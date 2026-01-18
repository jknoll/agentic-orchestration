"""TinyFish/Mino API client for AI-powered web extraction."""

import json
import os
from typing import Callable, Optional

import httpx


class TinyFishError(Exception):
    """TinyFish API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


# Type alias for progress callback
ProgressCallback = Callable[[str], None]


# Goal prompt for product metadata extraction
PRODUCT_METADATA_GOAL = """Extract the product metadata for this single product page. Return a JSON object with these fields:
- title: The product name
- description: Product description (full text)
- price: Price with currency symbol or code (e.g., "$199.99" or "USD 199.99")
- brand: Brand or manufacturer name
- images: List of product image URLs (full URLs, not relative paths)
- features: List of key product features or specifications"""


class TinyFishClient:
    """Async client for TinyFish/Mino AI web extraction API."""

    BASE_URL = "https://mino.ai"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the TinyFish client.

        Args:
            api_key: Mino API key. If not provided, reads from MINO_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("MINO_API_KEY")
        if not self.api_key:
            raise TinyFishError("Mino API key not provided. Set MINO_API_KEY env var.")

        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=120.0,  # Longer timeout for AI extraction
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self._client:
            await self._client.aclose()

    async def extract_product_metadata(
        self,
        url: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        """
        Extract product metadata from a URL using TinyFish AI.

        Args:
            url: The product page URL to extract metadata from
            on_progress: Optional callback for progress updates

        Returns:
            Dictionary with extracted product metadata

        Raises:
            TinyFishError: If extraction fails
        """
        if not self._client:
            raise TinyFishError("Client not initialized. Use 'async with' context.")

        payload = {
            "browser_profile": "stealth",
            "proxy_config": {
                "enabled": True,
                "country_code": "US",
            },
            "url": url,
            "goal": PRODUCT_METADATA_GOAL,
        }

        try:
            # Use streaming for SSE endpoint
            async with self._client.stream(
                "POST",
                "/v1/automation/run-sse",
                json=payload,
                timeout=180.0,  # Extended timeout for full extraction
            ) as response:
                response.raise_for_status()

                result_data = None
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Parse SSE data lines
                    if line.startswith("data: "):
                        try:
                            event_data = json.loads(line[6:])
                            event_type = event_data.get("type")

                            if event_type == "PROGRESS":
                                purpose = event_data.get("purpose", "")
                                print(f"[TinyFish] {purpose}")
                                # Call the progress callback if provided
                                if on_progress and purpose:
                                    on_progress(purpose)

                            elif event_type == "COMPLETE":
                                result_data = event_data.get("resultJson")
                                if on_progress:
                                    on_progress("Extraction complete")
                                break

                            elif event_type == "ERROR":
                                error_msg = event_data.get("errorMessage", "Unknown error")
                                raise TinyFishError(f"Extraction failed: {error_msg}")

                        except json.JSONDecodeError:
                            # Skip malformed JSON lines
                            continue

                if result_data is None:
                    raise TinyFishError("No result received from TinyFish")

                return result_data

        except httpx.HTTPStatusError as e:
            error_msg = _parse_error_response(e.response)
            raise TinyFishError(error_msg, status_code=e.response.status_code)
        except httpx.TimeoutException:
            raise TinyFishError("Request timed out - the page may be too complex")


def _parse_error_response(response: httpx.Response) -> str:
    """Parse an error response from TinyFish API."""
    status_code = response.status_code

    try:
        data = response.json()
        if isinstance(data, dict):
            if "message" in data:
                return data["message"]
            if "error" in data:
                return data["error"]
    except Exception:
        pass

    status_messages = {
        400: "Bad request - invalid parameters",
        401: "Invalid API key - check your MINO_API_KEY",
        402: "Insufficient credits - please add more credits to your Mino account",
        403: "Access forbidden - check your API key permissions",
        429: "Rate limit exceeded - please wait before retrying",
        500: "TinyFish server error - please try again later",
    }

    if status_code in status_messages:
        return status_messages[status_code]

    text = response.text.strip()
    if text:
        return f"API error ({status_code}): {text[:200]}"

    return f"API error ({status_code})"

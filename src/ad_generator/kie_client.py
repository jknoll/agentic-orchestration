"""Kie.ai API client for Veo 3 video generation."""

import asyncio
import os
from pathlib import Path
from typing import Optional

import httpx

from .models import AspectRatio, VideoGenerationRequest, VideoGenerationResult, VideoStatus


class KieAIError(Exception):
    """Kie.ai API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _parse_error_response(response: httpx.Response) -> str:
    """Parse an error response from Kie.ai API."""
    status_code = response.status_code

    try:
        data = response.json()
        if isinstance(data, dict):
            msg = data.get("msg") or data.get("message") or ""
            # Check for credit-related errors in the message
            if _is_credit_error(msg) or _is_credit_error(str(data)):
                return "Insufficient credits - please add more credits to your Kie.ai account at https://kie.ai"
            if msg:
                return msg
    except Exception:
        pass

    status_messages = {
        400: "Bad request - invalid parameters",
        401: "Invalid API key - check your KIE_API_KEY",
        402: "Insufficient credits - please add more credits to your Kie.ai account at https://kie.ai",
        403: "Access forbidden - check your API key permissions",
        429: "Rate limit exceeded - please wait before retrying",
        500: "Kie.ai server error - please try again later",
    }

    if status_code in status_messages:
        return status_messages[status_code]

    text = response.text.strip()
    if text:
        return f"API error ({status_code}): {text[:200]}"

    return f"API error ({status_code})"


def _is_credit_error(text: str) -> bool:
    """Check if an error message indicates insufficient credits."""
    if not text:
        return False
    text_lower = text.lower()
    credit_indicators = [
        "insufficient",
        "credit",
        "balance",
        "quota",
        "limit exceeded",
        "no remaining",
        "payment",
        "subscription",
        "top up",
        "recharge",
        "out of",
        "run out",
        "exhausted",
    ]
    return any(indicator in text_lower for indicator in credit_indicators)


class KieAIClient:
    """Async client for Kie.ai Veo 3 video generation."""

    BASE_URL = "https://api.kie.ai"

    def __init__(self, api_key: Optional[str] = None, use_fast: bool = True):
        """
        Initialize the Kie.ai client.

        Args:
            api_key: Kie.ai API key. Reads from KIE_API_KEY env var if not provided.
            use_fast: Use veo3_fast model (cheaper, faster) vs veo3 (higher quality).
        """
        self.api_key = api_key or os.environ.get("KIE_API_KEY")
        if not self.api_key:
            raise KieAIError("Kie.ai API key not provided. Set KIE_API_KEY env var.")

        self.use_fast = use_fast
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self._client:
            await self._client.aclose()

    async def generate_video(
        self,
        request: VideoGenerationRequest,
    ) -> VideoGenerationResult:
        """
        Submit a video generation request to Veo 3.

        Args:
            request: Video generation parameters

        Returns:
            VideoGenerationResult with task_id
        """
        if not self._client:
            raise KieAIError("Client not initialized. Use 'async with' context.")

        model = "veo3_fast" if self.use_fast else "veo3"

        # Map aspect ratio to Kie.ai format
        aspect_ratio = request.aspect_ratio.value if request.aspect_ratio else "16:9"

        payload = {
            "prompt": request.prompt,
            "model": model,
            "generationType": "TEXT_2_VIDEO",
            "aspect_ratio": aspect_ratio,
            "enableTranslation": False,  # Prompts are already in English
        }
        # Note: Veo 3 generates ~8 second clips by default, duration not configurable

        try:
            response = await self._client.post("/api/v1/veo/generate", json=payload)
            response.raise_for_status()
            data = response.json()

            # Check for error codes in response body
            response_code = data.get("code")
            error_msg = data.get("msg", "")

            # Check for credit-related errors
            if _is_credit_error(error_msg) or _is_credit_error(str(data)):
                raise KieAIError(
                    "Insufficient credits - please add more credits to your Kie.ai account at https://kie.ai",
                    status_code=402,
                )

            if response_code != 200:
                if not error_msg:
                    error_msg = "Unknown error"
                raise KieAIError(f"API error: {error_msg}", status_code=response_code)

            task_id = data.get("data", {}).get("taskId")
            if not task_id:
                raise KieAIError("No taskId in response - possible API error")

            return VideoGenerationResult(
                task_id=task_id,
                status=VideoStatus.PENDING,
            )
        except httpx.HTTPStatusError as e:
            error_msg = _parse_error_response(e.response)
            raise KieAIError(error_msg, status_code=e.response.status_code)

    async def check_status(self, task_id: str) -> VideoGenerationResult:
        """
        Check the status of a video generation task.

        Args:
            task_id: The task ID returned from generate_video

        Returns:
            VideoGenerationResult with current status
        """
        if not self._client:
            raise KieAIError("Client not initialized. Use 'async with' context.")

        try:
            response = await self._client.get(
                "/api/v1/veo/record-info",
                params={"taskId": task_id},
            )
            response.raise_for_status()
            data = response.json()

            # Check for credit-related errors
            error_msg = data.get("msg", "")
            if _is_credit_error(error_msg) or _is_credit_error(str(data)):
                raise KieAIError(
                    "Insufficient credits - please add more credits to your Kie.ai account at https://kie.ai",
                    status_code=402,
                )

            if data.get("code") != 200:
                if not error_msg:
                    error_msg = "Unknown error"
                raise KieAIError(f"API error: {error_msg}")

            task_data = data.get("data", {})
            success_flag = task_data.get("successFlag")

            # Map successFlag to our status enum
            # 0: Generating, 1: Success, 2: Failed, 3: Generation Failed
            if success_flag == 0:
                status = VideoStatus.PROCESSING
            elif success_flag == 1:
                status = VideoStatus.COMPLETED
            else:
                status = VideoStatus.FAILED

            # Extract video URL if completed
            video_url = None
            if status == VideoStatus.COMPLETED:
                response_data = task_data.get("response", {})
                result_urls = response_data.get("resultUrls", [])
                if result_urls:
                    video_url = result_urls[0]

            error_message = None
            if status == VideoStatus.FAILED:
                error_message = task_data.get("errorMessage", "Video generation failed")

            return VideoGenerationResult(
                task_id=task_id,
                status=status,
                video_url=video_url,
                error_message=error_message,
            )
        except httpx.HTTPStatusError as e:
            error_msg = _parse_error_response(e.response)
            raise KieAIError(
                f"Status check failed: {error_msg}",
                status_code=e.response.status_code,
            )

    async def wait_for_completion(
        self,
        task_id: str,
        timeout_seconds: int = 600,
        poll_interval: float = 10.0,
    ) -> VideoGenerationResult:
        """
        Poll until video generation completes or times out.

        Args:
            task_id: The task ID to poll
            timeout_seconds: Maximum time to wait (default 10 minutes)
            poll_interval: Seconds between polls (default 10 seconds)

        Returns:
            Final VideoGenerationResult

        Raises:
            KieAIError: If timeout or generation fails
        """
        elapsed = 0.0

        while elapsed < timeout_seconds:
            result = await self.check_status(task_id)

            if result.status == VideoStatus.COMPLETED:
                return result
            elif result.status == VideoStatus.FAILED:
                raise KieAIError(f"Video generation failed: {result.error_message}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise KieAIError(f"Timeout waiting for video generation after {timeout_seconds}s")

    async def download_video(
        self,
        video_url: str,
        output_path: Path,
    ) -> Path:
        """
        Download a completed video to a local file.

        Args:
            video_url: URL of the generated video
            output_path: Local path to save the video

        Returns:
            Path to the downloaded file
        """
        if not self._client:
            raise KieAIError("Client not initialized. Use 'async with' context.")

        # Create parent directories if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with self._client.stream("GET", video_url) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

            return output_path
        except httpx.HTTPStatusError as e:
            error_msg = _parse_error_response(e.response)
            raise KieAIError(
                f"Download failed: {error_msg}",
                status_code=e.response.status_code,
            )

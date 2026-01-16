"""AgentQL API client for product extraction."""

import os
from typing import Optional

import httpx

from .models import ProductResearch


class AgentQLError(Exception):
    """AgentQL API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AgentQLClient:
    """Async client for AgentQL/TinyFish API."""

    ENDPOINT = "https://api.agentql.com/v1/query-data"

    DEFAULT_FIELDS = [
        "product_name",
        "price",
        "description",
        "features",
        "specifications",
        "benefits",
        "target_audience",
        "images",
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("AGENTQL_API_KEY")
        if not self.api_key:
            raise AgentQLError("AgentQL API key not provided")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    def _build_query(self, fields: list[str]) -> str:
        """Build AgentQL query from field list."""
        query_parts = []
        array_fields = {"features", "specifications", "benefits", "images"}
        for field in fields:
            if field in array_fields:
                query_parts.append(f"    {field}[]")
            else:
                query_parts.append(f"    {field}")
        return "{\n" + "\n".join(query_parts) + "\n}"

    async def extract_product(
        self,
        url: str,
        fields: Optional[list[str]] = None,
    ) -> ProductResearch:
        """Extract product data from URL."""
        if not self._client:
            raise AgentQLError("Client not initialized. Use 'async with' context.")

        fields = fields or self.DEFAULT_FIELDS
        query = self._build_query(fields)

        try:
            response = await self._client.post(
                self.ENDPOINT,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "url": url,
                    "query": query,
                    "is_scroll_to_bottom_enabled": True,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract nested data
            result_data = data.get("data", data)

            return ProductResearch(
                product_name=result_data.get("product_name"),
                price=result_data.get("price"),
                description=result_data.get("description"),
                features=result_data.get("features", []),
                specifications=result_data.get("specifications", []),
                benefits=result_data.get("benefits", []),
                target_audience=result_data.get("target_audience"),
                images=result_data.get("images", []),
                url=url,
            )
        except httpx.HTTPStatusError as e:
            raise AgentQLError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )

"""Yutori Research API client for product research."""

import asyncio
import os
from typing import Optional

import httpx

from .models import (
    ProductResearchResult,
    ResearchStatus,
    ResearchTaskResponse,
)


class YutoriError(Exception):
    """Yutori API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class YutoriClient:
    """Async client for Yutori Research API."""

    BASE_URL = "https://api.yutori.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Yutori client.

        Args:
            api_key: Yutori API key. If not provided, reads from YUTORI_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("YUTORI_API_KEY")
        if not self.api_key:
            raise YutoriError("Yutori API key not provided")

        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self._client:
            await self._client.aclose()

    def _build_task_spec(self) -> dict:
        """Build the task_spec for structured product research output."""
        return {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "price": {
                    "type": "object",
                    "properties": {
                        "base": {"type": "string"},
                        "tiers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "variant": {"type": "string"},
                                    "price": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "key_features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
                "benefits": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "unique_selling_points": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "ratings": {
                    "type": "object",
                    "properties": {
                        "average_score": {"type": "number"},
                        "total_reviews": {"type": "integer"},
                        "breakdown": {
                            "type": "object",
                            "properties": {
                                "5_star": {"type": "string"},
                                "4_star": {"type": "string"},
                                "3_star": {"type": "string"},
                                "2_star": {"type": "string"},
                                "1_star": {"type": "string"},
                            },
                        },
                    },
                },
                "target_audience": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "user_reviews": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "author": {"type": "string"},
                            "rating": {"type": "integer"},
                            "title": {"type": "string"},
                            "comment": {"type": "string"},
                            "verified_purchase": {"type": "boolean"},
                            "date": {"type": "string"},
                        },
                        "required": ["author", "comment"],
                    },
                    "maxItems": 5,
                },
            },
            "required": ["product_name", "key_features"],
        }

    def _build_research_query(self, product_name: str) -> str:
        """Build the research query prompt for Yutori."""
        return f"""Research the product: "{product_name}"

Gather comprehensive information including:
1. Current pricing (base price and tier-based pricing if applicable)
2. Top 3-5 key features that make this product stand out
3. Main benefits users get from using this product (what problems it solves)
4. Unique selling points compared to competitors
5. User ratings and reviews (average rating, total reviews, rating distribution by stars)
6. Target audience segments (who should buy this product)
7. Sample user reviews (3-5 reviews with author name, rating, title, comment, and date)

Focus on factual, up-to-date information from official sources, e-commerce platforms, and trusted review sites."""

    def _parse_result(self, data: dict) -> ProductResearchResult:
        """Parse the API result into ProductResearchResult model."""
        # Handle ratings breakdown conversion
        ratings = None
        if "ratings" in data and data["ratings"]:
            ratings_data = data["ratings"]
            breakdown = None
            if "breakdown" in ratings_data and ratings_data["breakdown"]:
                bd = ratings_data["breakdown"]
                from .models import RatingBreakdown

                breakdown = RatingBreakdown(
                    five_star=bd.get("5_star"),
                    four_star=bd.get("4_star"),
                    three_star=bd.get("3_star"),
                    two_star=bd.get("2_star"),
                    one_star=bd.get("1_star"),
                )
            from .models import RatingsSummary

            ratings = RatingsSummary(
                average_score=ratings_data.get("average_score"),
                total_reviews=ratings_data.get("total_reviews"),
                breakdown=breakdown,
            )

        # Handle user reviews conversion
        user_reviews = []
        if "user_reviews" in data and data["user_reviews"]:
            from .models import UserReview

            for review in data["user_reviews"]:
                user_reviews.append(
                    UserReview(
                        author=review.get("author", "Anonymous"),
                        rating=review.get("rating"),
                        title=review.get("title"),
                        comment=review.get("comment", ""),
                        verified_purchase=review.get("verified_purchase", False),
                        date=review.get("date"),
                    )
                )

        return ProductResearchResult(
            product_name=data.get("product_name", "Unknown Product"),
            price=data.get("price"),
            key_features=data.get("key_features", []),
            benefits=data.get("benefits", []),
            unique_selling_points=data.get("unique_selling_points", []),
            ratings=ratings,
            target_audience=data.get("target_audience", []),
            user_reviews=user_reviews,
        )

    async def create_research_task(
        self,
        product_name: str,
    ) -> ResearchTaskResponse:
        """
        Create a new product research task.

        Args:
            product_name: Name of the product to research

        Returns:
            ResearchTaskResponse with task_id and initial status
        """
        if not self._client:
            raise YutoriError("Client not initialized. Use 'async with' context.")

        payload = {
            "query": self._build_research_query(product_name),
            "task_spec": self._build_task_spec(),
        }

        try:
            response = await self._client.post("/research/tasks", json=payload)
            response.raise_for_status()
            data = response.json()

            return ResearchTaskResponse(
                task_id=data["task_id"],
                status=ResearchStatus(data.get("status", "queued")),
                view_url=data.get("view_url"),
            )
        except httpx.HTTPStatusError as e:
            raise YutoriError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )

    async def get_task_status(self, task_id: str) -> ResearchTaskResponse:
        """
        Get the status of a research task.

        Args:
            task_id: The task ID from create_research_task

        Returns:
            ResearchTaskResponse with current status and result if completed
        """
        if not self._client:
            raise YutoriError("Client not initialized. Use 'async with' context.")

        try:
            response = await self._client.get(f"/research/tasks/{task_id}")
            response.raise_for_status()
            data = response.json()

            status = ResearchStatus(data.get("status", "queued"))

            result = None
            if status == ResearchStatus.SUCCEEDED and "result" in data:
                result = self._parse_result(data["result"])

            error_message = None
            if status == ResearchStatus.FAILED:
                error_message = data.get("error", "Unknown error")

            return ResearchTaskResponse(
                task_id=task_id,
                status=status,
                view_url=data.get("view_url"),
                result=result,
                error_message=error_message,
            )
        except httpx.HTTPStatusError as e:
            raise YutoriError(
                f"Status check failed: {e.response.text}",
                status_code=e.response.status_code,
            )

    async def wait_for_completion(
        self,
        task_id: str,
        timeout_seconds: int = 180,
        poll_interval: float = 3.0,
    ) -> ResearchTaskResponse:
        """
        Poll until research task completes or times out.

        Args:
            task_id: The task ID to poll
            timeout_seconds: Maximum time to wait (default 3 minutes)
            poll_interval: Seconds between polls (default 3 seconds)

        Returns:
            Final ResearchTaskResponse with result

        Raises:
            YutoriError: If timeout or research fails
        """
        elapsed = 0.0

        while elapsed < timeout_seconds:
            response = await self.get_task_status(task_id)

            if response.status == ResearchStatus.SUCCEEDED:
                return response
            elif response.status == ResearchStatus.FAILED:
                raise YutoriError(f"Research task failed: {response.error_message}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise YutoriError(f"Timeout waiting for research after {timeout_seconds}s")

    async def research_product(
        self,
        product_name: str,
        timeout_seconds: int = 180,
    ) -> ProductResearchResult:
        """
        High-level method: research a product and return structured results.

        Args:
            product_name: Name of the product to research
            timeout_seconds: Maximum time to wait for research

        Returns:
            ProductResearchResult with structured research data
        """
        task = await self.create_research_task(product_name)
        response = await self.wait_for_completion(task.task_id, timeout_seconds)

        if not response.result:
            raise YutoriError("Research completed but no result returned")

        # Add the view_url to the result for reference
        response.result.research_url = response.view_url
        return response.result

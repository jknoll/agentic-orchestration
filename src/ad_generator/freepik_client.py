"""FreePik API client for video generation."""

import asyncio
import os
from pathlib import Path
from typing import Optional

import httpx

from .models import VideoGenerationRequest, VideoGenerationResult, VideoResolution, VideoStatus


class FreePikError(Exception):
    """FreePik API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class FreePikClient:
    """Async client for FreePik video generation API."""

    BASE_URL = "https://api.freepik.com"

    # Model endpoint mappings
    # Note: Veo 3 may be added when available via API
    TEXT_TO_VIDEO_MODELS = {
        "wan-v2-6-720p": "/v1/ai/text-to-video/wan-v2-6-720p",
        "wan-v2-6-1080p": "/v1/ai/text-to-video/wan-v2-6-1080p",
    }

    # Size mappings based on resolution
    SIZE_MAP = {
        VideoResolution.HD_720P: "1280*720",
        VideoResolution.FHD_1080P: "1920*1080",
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the FreePik client.

        Args:
            api_key: FreePik API key. If not provided, reads from FREEPIK_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("FREEPIK_API_KEY")
        if not self.api_key:
            raise FreePikError("FreePik API key not provided")

        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "x-freepik-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self._client:
            await self._client.aclose()

    def _get_endpoint(self, resolution: VideoResolution) -> str:
        """Get the appropriate endpoint based on resolution."""
        if resolution == VideoResolution.FHD_1080P:
            return self.TEXT_TO_VIDEO_MODELS["wan-v2-6-1080p"]
        return self.TEXT_TO_VIDEO_MODELS["wan-v2-6-720p"]

    async def generate_video(
        self,
        request: VideoGenerationRequest,
        webhook_url: Optional[str] = None,
    ) -> VideoGenerationResult:
        """
        Submit a video generation request.

        Args:
            request: Video generation parameters
            webhook_url: Optional callback URL for async notification

        Returns:
            VideoGenerationResult with task_id and initial status
        """
        if not self._client:
            raise FreePikError("Client not initialized. Use 'async with' context.")

        endpoint = self._get_endpoint(request.resolution)

        payload = {
            "prompt": request.prompt,
            "size": self.SIZE_MAP[request.resolution],
            "duration": "5",  # Default to 5 seconds for ads
            "enable_prompt_expansion": True,  # Let AI enhance prompts
            "shot_type": "single",
        }

        if webhook_url:
            payload["webhook_url"] = webhook_url

        try:
            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            return VideoGenerationResult(
                task_id=data["data"]["task_id"],
                status=VideoStatus.PENDING,
            )
        except httpx.HTTPStatusError as e:
            raise FreePikError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )

    async def check_status(
        self,
        task_id: str,
        resolution: VideoResolution = VideoResolution.HD_720P,
    ) -> VideoGenerationResult:
        """
        Check the status of a video generation task.

        Args:
            task_id: The task ID returned from generate_video
            resolution: The resolution used in the original request

        Returns:
            VideoGenerationResult with current status
        """
        if not self._client:
            raise FreePikError("Client not initialized. Use 'async with' context.")

        endpoint = f"{self._get_endpoint(resolution)}/{task_id}"

        try:
            response = await self._client.get(endpoint)
            response.raise_for_status()
            data = response.json()

            task_data = data.get("data", {})
            status_str = task_data.get("status", "").lower()

            # Map API status to our enum
            if status_str in ("created", "pending", "queued"):
                status = VideoStatus.PENDING
            elif status_str in ("processing", "in_progress"):
                status = VideoStatus.PROCESSING
            elif status_str in ("completed", "done", "success"):
                status = VideoStatus.COMPLETED
            else:
                status = VideoStatus.FAILED

            # Extract video URL if completed
            video_url = None
            if status == VideoStatus.COMPLETED:
                # Video URL is in the "generated" array
                generated = task_data.get("generated", [])
                if generated and len(generated) > 0:
                    video_url = generated[0]
                # Fallback to other possible fields
                if not video_url:
                    video_url = task_data.get("video", {}).get("url")
                if not video_url:
                    video_url = task_data.get("output", {}).get("url")
                if not video_url:
                    video_url = task_data.get("url")

            error_message = None
            if status == VideoStatus.FAILED:
                error_message = task_data.get("error", "Unknown error")

            return VideoGenerationResult(
                task_id=task_id,
                status=status,
                video_url=video_url,
                error_message=error_message,
            )
        except httpx.HTTPStatusError as e:
            raise FreePikError(
                f"Status check failed: {e.response.text}",
                status_code=e.response.status_code,
            )

    async def wait_for_completion(
        self,
        task_id: str,
        resolution: VideoResolution = VideoResolution.HD_720P,
        timeout_seconds: int = 300,
        poll_interval: float = 5.0,
    ) -> VideoGenerationResult:
        """
        Poll until video generation completes or times out.

        Args:
            task_id: The task ID to poll
            resolution: The resolution used in the original request
            timeout_seconds: Maximum time to wait (default 5 minutes)
            poll_interval: Seconds between polls (default 5 seconds)

        Returns:
            Final VideoGenerationResult

        Raises:
            FreePikError: If timeout or generation fails
        """
        elapsed = 0.0

        while elapsed < timeout_seconds:
            result = await self.check_status(task_id, resolution)

            if result.status == VideoStatus.COMPLETED:
                return result
            elif result.status == VideoStatus.FAILED:
                raise FreePikError(
                    f"Video generation failed: {result.error_message}"
                )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise FreePikError(f"Timeout waiting for video generation after {timeout_seconds}s")

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
            raise FreePikError("Client not initialized. Use 'async with' context.")

        # Create parent directories if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Stream download to handle large files
            async with self._client.stream("GET", video_url) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

            return output_path
        except httpx.HTTPStatusError as e:
            raise FreePikError(
                f"Download failed: {e.response.text}",
                status_code=e.response.status_code,
            )

"""FreePik API client for video generation."""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import httpx

from .models import (
    AspectRatio,
    VideoDuration,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoResolution,
    VideoStatus,
)


class FreePikError(Exception):
    """FreePik API error."""

    def __init__(self, message: str, status_code: Optional[int] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def _parse_error_response(response: httpx.Response) -> tuple[str, Optional[str]]:
    """
    Parse an error response from FreePik API.

    Returns:
        Tuple of (human-readable message, error_code if available)
    """
    status_code = response.status_code
    error_code = None

    # Try to parse JSON error response
    try:
        data = response.json()

        # FreePik error format: {"error": {"code": "...", "message": "..."}}
        # or {"message": "...", "code": "..."}
        if isinstance(data, dict):
            error_obj = data.get("error", data)
            if isinstance(error_obj, dict):
                error_code = error_obj.get("code")
                message = error_obj.get("message")
                if message:
                    return message, error_code

            # Try top-level message
            if "message" in data:
                return data["message"], data.get("code")

    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback to status code messages
    status_messages = {
        400: "Bad request - invalid parameters",
        401: "Invalid API key",
        402: "Insufficient credits - please add more credits to your FreePik account",
        403: "Access forbidden - check your API key permissions",
        404: "Resource not found",
        429: "Rate limit exceeded - please wait before retrying",
        500: "FreePik server error - please try again later",
        502: "FreePik service temporarily unavailable",
        503: "FreePik service temporarily unavailable",
    }

    if status_code in status_messages:
        return status_messages[status_code], error_code

    # Last resort: use raw response text
    text = response.text.strip()
    if text:
        return f"API error ({status_code}): {text[:200]}", error_code

    return f"API error ({status_code})", error_code


class FreePikClient:
    """Async client for FreePik video generation API."""

    BASE_URL = "https://api.freepik.com"

    # Model endpoint mappings
    # Note: Veo 3 may be added when available via API
    TEXT_TO_VIDEO_MODELS = {
        "wan-v2-6-720p": "/v1/ai/text-to-video/wan-v2-6-720p",
        "wan-v2-6-1080p": "/v1/ai/text-to-video/wan-v2-6-1080p",
    }

    # Size mappings based on resolution and aspect ratio
    SIZE_MAP = {
        (VideoResolution.HD_720P, AspectRatio.LANDSCAPE_16_9): "1280*720",
        (VideoResolution.HD_720P, AspectRatio.PORTRAIT_9_16): "720*1280",
        (VideoResolution.FHD_1080P, AspectRatio.LANDSCAPE_16_9): "1920*1080",
        (VideoResolution.FHD_1080P, AspectRatio.PORTRAIT_9_16): "1080*1920",
    }

    # Valid duration values for FreePik (5, 10, 15 seconds)
    VALID_DURATIONS = {5, 10, 15}

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

        # Map duration to valid FreePik values (5, 10, or 15)
        duration = request.duration.value
        if duration not in self.VALID_DURATIONS:
            # Round to nearest valid duration
            if duration <= 5:
                duration = 5
            elif duration <= 10:
                duration = 10
            else:
                duration = 15

        # Get size based on resolution and aspect ratio
        size_key = (request.resolution, request.aspect_ratio)
        size = self.SIZE_MAP.get(size_key, "1280*720")

        payload = {
            "prompt": request.prompt,
            "size": size,
            "duration": str(duration),
            "enable_prompt_expansion": True,  # Let AI enhance prompts
            "shot_type": "single",
            "audio": request.with_audio,  # Enable audio generation
        }

        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

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
            message, error_code = _parse_error_response(e.response)
            raise FreePikError(
                message,
                status_code=e.response.status_code,
                error_code=error_code,
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
            message, error_code = _parse_error_response(e.response)
            raise FreePikError(
                f"Status check failed: {message}",
                status_code=e.response.status_code,
                error_code=error_code,
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
            message, error_code = _parse_error_response(e.response)
            raise FreePikError(
                f"Download failed: {message}",
                status_code=e.response.status_code,
                error_code=error_code,
            )

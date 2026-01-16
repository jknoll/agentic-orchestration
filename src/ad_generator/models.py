"""Data models for the ad generator."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, HttpUrl


class ProductMetadata(BaseModel):
    """Metadata extracted from a product detail page."""

    title: str
    description: Optional[str] = None
    images: list[str] = []
    price: Optional[str] = None
    brand: Optional[str] = None
    features: list[str] = []
    url: str


class VideoResolution(str, Enum):
    """Supported video resolutions."""

    HD_720P = "720p"
    FHD_1080P = "1080p"


class VideoStatus(str, Enum):
    """Video generation status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoGenerationRequest(BaseModel):
    """Request to generate a video."""

    prompt: str
    resolution: VideoResolution = VideoResolution.HD_720P
    with_audio: bool = True


class VideoGenerationResult(BaseModel):
    """Result of video generation."""

    task_id: str
    status: VideoStatus
    video_url: Optional[str] = None
    error_message: Optional[str] = None


class AdScene(BaseModel):
    """A scene in the ad script."""

    description: str
    duration_seconds: float = 2.0
    narration: Optional[str] = None
    visual_notes: Optional[str] = None


class AdScript(BaseModel):
    """Generated ad script."""

    product_name: str
    hook: str
    scenes: list[AdScene]
    call_to_action: str
    total_duration_seconds: float = 8.0


class GenerationOutput(BaseModel):
    """Final output of the ad generation process."""

    product: ProductMetadata
    script: AdScript
    video_prompt: str
    video_result: VideoGenerationResult
    output_path: Optional[str] = None

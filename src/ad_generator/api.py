"""FastAPI server for the ad generator."""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import AdGeneratorAgent
from .models import (
    AspectRatio,
    GenerationOutput,
    ProductMetadata,
    VideoDuration,
    VideoResolution,
)

# Load environment variables
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


class JobStatus(str, Enum):
    """Status of a generation job."""
    PENDING = "pending"
    EXTRACTING = "extracting"
    GENERATING_PROMPT = "generating_prompt"
    GENERATING_VIDEO = "generating_video"
    COMPLETE = "complete"
    FAILED = "failed"


class GenerateRequest(BaseModel):
    """Request to generate an ad."""
    url: str
    duration: int = 8
    resolution: str = "720p"
    aspect_ratio: str = "16:9"


class JobInfo(BaseModel):
    """Information about a generation job."""
    job_id: str
    status: JobStatus
    progress: int = 0
    message: str = ""
    product: Optional[dict] = None
    video_url: Optional[str] = None
    video_prompt: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


# In-memory job storage
jobs: dict[str, dict] = {}


app = FastAPI(title="AdFlow API", version="1.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def update_job(job_id: str, **kwargs):
    """Update job status."""
    if job_id in jobs:
        jobs[job_id].update(kwargs)
        jobs[job_id]["updated_at"] = datetime.now().isoformat()


async def run_generation(job_id: str, request: GenerateRequest):
    """Run the ad generation workflow."""
    try:
        # Parse parameters
        duration = VideoDuration(request.duration)
        resolution = VideoResolution.FHD_1080P if request.resolution == "1080p" else VideoResolution.HD_720P
        aspect_ratio = AspectRatio.PORTRAIT_9_16 if request.aspect_ratio == "9:16" else AspectRatio.LANDSCAPE_16_9

        # Update status: extracting
        update_job(job_id, status=JobStatus.EXTRACTING, progress=10, message="Extracting product metadata...")

        # Create agent with progress callback
        def on_tool_call(tool_name: str, args: dict):
            if tool_name == "get_product_metadata":
                update_job(job_id, status=JobStatus.EXTRACTING, progress=20, message="Fetching product information...")
            elif tool_name == "generate_video":
                update_job(job_id, status=JobStatus.GENERATING_VIDEO, progress=60, message="Generating video...")

        # Create output directory for this job
        output_dir = OUTPUT_DIR / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        agent = AdGeneratorAgent(
            output_dir=output_dir,
            use_veo3=False,
            veo3_quality=False,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            on_tool_call=on_tool_call,
        )

        # Update status: generating prompt
        update_job(job_id, status=JobStatus.GENERATING_PROMPT, progress=30, message="Crafting video prompt...")

        # Run generation
        result: GenerationOutput = await agent.generate_ad(request.url)

        # Extract video URL
        video_url = None
        if result.video_results:
            for vr in result.video_results:
                if vr.local_path:
                    # Create relative URL for serving
                    video_url = f"/api/video/{job_id}/{Path(vr.local_path).name}"
                    break

        # Update with product metadata
        product_dict = None
        if result.product:
            product_dict = {
                "title": result.product.title,
                "description": result.product.description,
                "price": result.product.price,
                "brand": result.product.brand,
                "features": result.product.features,
                "images": result.product.images[:3] if result.product.images else [],
            }

        # Update status: complete
        update_job(
            job_id,
            status=JobStatus.COMPLETE,
            progress=100,
            message="Video generated successfully!",
            product=product_dict,
            video_url=video_url,
            video_prompt=result.video_prompt,
        )

    except Exception as e:
        update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=0,
            message="Generation failed",
            error=str(e),
        )


@app.post("/api/generate")
async def generate_ad(request: GenerateRequest, background_tasks: BackgroundTasks) -> dict:
    """Start a new ad generation job."""
    job_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "progress": 0,
        "message": "Job queued...",
        "product": None,
        "video_url": None,
        "video_prompt": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "request_url": request.url,
    }

    # Start generation in background
    background_tasks.add_task(run_generation, job_id, request)

    return {"job_id": job_id, "status": "pending"}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str) -> JobInfo:
    """Get the status of a generation job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobInfo(**jobs[job_id])


@app.get("/api/video/{job_id}/{filename}")
async def serve_video(job_id: str, filename: str):
    """Serve a generated video file."""
    video_path = OUTPUT_DIR / job_id / filename

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=filename,
    )


# Mount static files for index.html (must be last)
app.mount("/", StaticFiles(directory=str(PROJECT_ROOT), html=True), name="static")

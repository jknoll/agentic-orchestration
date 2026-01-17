"""FastAPI server for AdFlow web interface."""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Optional

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

from .agent import AdGeneratorAgent

# Output directory for generated videos
OUTPUT_DIR = Path("./output")


class JobStage(str, Enum):
    """Job processing stage."""

    QUEUED = "queued"
    EXTRACTING_METADATA = "extracting_metadata"
    GENERATING_PROMPT = "generating_prompt"
    GENERATING_VIDEO = "generating_video"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(BaseModel):
    """Status of a generation job."""

    job_id: str
    product_url: str
    stage: JobStage
    progress_percent: int = 0
    message: str = ""
    product: Optional[dict] = None
    video_prompt: Optional[str] = None
    video_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GenerateRequest(BaseModel):
    """Request to generate a video ad."""

    url: HttpUrl


class GenerateResponse(BaseModel):
    """Response from starting a generation job."""

    job_id: str
    status: str


class JobStore:
    """Thread-safe in-memory job storage."""

    def __init__(self):
        self._jobs: dict[str, JobStatus] = {}
        self._lock = Lock()

    def create(self, product_url: str) -> str:
        """Create a new job and return its ID."""
        job_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow()
        with self._lock:
            self._jobs[job_id] = JobStatus(
                job_id=job_id,
                product_url=product_url,
                stage=JobStage.QUEUED,
                progress_percent=0,
                message="Job queued",
                created_at=now,
                updated_at=now,
            )
        return job_id

    def update(self, job_id: str, **kwargs) -> None:
        """Update a job's status."""
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                job.updated_at = datetime.utcnow()

    def get(self, job_id: str) -> Optional[JobStatus]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_all(self) -> list[JobStatus]:
        """List all jobs."""
        return list(self._jobs.values())


# Global job store
job_store = JobStore()

# Create FastAPI app
app = FastAPI(
    title="AdFlow API",
    description="Generate video advertisements from product URLs",
    version="1.0.0",
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def run_generation_task(job_id: str, product_url: str) -> None:
    """Background task that runs the agent and updates job status."""
    try:
        job_store.update(
            job_id,
            stage=JobStage.EXTRACTING_METADATA,
            progress_percent=10,
            message="Starting generation...",
        )

        def on_tool_call(name: str, args: dict) -> None:
            """Callback to update job status based on tool calls."""
            if name == "get_product_metadata":
                job_store.update(
                    job_id,
                    stage=JobStage.EXTRACTING_METADATA,
                    progress_percent=15,
                    message="Extracting product metadata...",
                )
            elif name == "generate_video":
                job_store.update(
                    job_id,
                    stage=JobStage.GENERATING_VIDEO,
                    progress_percent=50,
                    message="Generating video (this may take a few minutes)...",
                    video_prompt=args.get("prompt"),
                )

        def on_tool_result(name: str, args: dict, result: any) -> None:
            """Callback to update job status with tool results."""
            if name == "get_product_metadata":
                job_store.update(
                    job_id,
                    stage=JobStage.GENERATING_PROMPT,
                    progress_percent=35,
                    message="Creating video prompt...",
                    product=result,  # Product metadata dict
                )

        # Create output directory for this job
        job_output_dir = OUTPUT_DIR / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        # Create and run the agent
        agent = AdGeneratorAgent(
            output_dir=job_output_dir,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )

        result = await agent.generate_ad(product_url)

        # Get video path from results
        video_path = None
        if result.video_results:
            video_path = result.video_results[0].local_path

        # Update job with final results
        job_store.update(
            job_id,
            stage=JobStage.COMPLETED,
            progress_percent=100,
            message="Video generation complete!",
            product=result.product.model_dump(),
            video_prompt=result.video_prompt,
            video_path=video_path,
        )

    except Exception as e:
        job_store.update(
            job_id,
            stage=JobStage.FAILED,
            progress_percent=0,
            message="Generation failed",
            error=str(e),
        )


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_ad(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Start a new ad generation job."""
    product_url = str(request.url)
    job_id = job_store.create(product_url)

    # Run generation in background
    background_tasks.add_task(run_generation_task, job_id, product_url)

    return GenerateResponse(job_id=job_id, status="queued")


@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the status of a generation job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs."""
    return job_store.list_all()


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    """Download the generated video."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.video_path:
        raise HTTPException(status_code=404, detail="Video not yet available")

    video_path = Path(job.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"adflow_{job_id}.mp4",
    )


# Serve frontend static files - calculate path relative to this file
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent.parent
frontend_path = _PROJECT_ROOT / "frontend"


@app.get("/")
async def root():
    """Serve the frontend HTML."""
    index_path = frontend_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {
        "message": "AdFlow API - Frontend not found",
        "expected_path": str(index_path),
        "project_root": str(_PROJECT_ROOT),
    }


# Mount static files after the root route
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


def main():
    """Entry point for the API server."""
    import uvicorn

    uvicorn.run(
        "ad_generator.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()

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

import json

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

from .agent import AdGeneratorAgent
from .showcase_parser import parse_readme, ParsedReadme

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


class AgentStatus(str, Enum):
    """Individual agent status."""

    STANDBY = "standby"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


class AgentStatuses(BaseModel):
    """Status of each agent in the pipeline."""

    research: AgentStatus = AgentStatus.STANDBY
    content: AgentStatus = AgentStatus.STANDBY
    video: AgentStatus = AgentStatus.STANDBY


class LogEntry(BaseModel):
    """A log entry with timestamp."""

    timestamp: datetime
    source: str  # e.g., "TinyFish", "FreePik", "Agent"
    message: str


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
    # New fields for detailed tracking
    agents: AgentStatuses = AgentStatuses()
    logs: list[LogEntry] = []


class GenerateRequest(BaseModel):
    """Request to generate a video ad."""

    url: HttpUrl


class GenerateResponse(BaseModel):
    """Response from starting a generation job."""

    job_id: str
    status: str


# Showcase API models
class ProductShowcaseMetadata(BaseModel):
    """Product metadata for showcase display."""

    title: str
    brand: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    product_url: Optional[str] = None


class VideoShowcaseItem(BaseModel):
    """A single video item for the showcase."""

    folder_name: str
    video_path: str
    provider: str  # "freepik" or "veo3"
    task_id: str
    product: ProductShowcaseMetadata
    prompt: Optional[str] = None
    generated_at: Optional[str] = None
    is_featured: bool = False
    featured_order: Optional[int] = None
    carousel_title: Optional[str] = None


class ShowcaseStats(BaseModel):
    """Aggregate statistics for the showcase."""

    total_videos: int
    total_products: int
    total_brands: int
    freepik_count: int
    veo3_count: int


class ShowcaseResponse(BaseModel):
    """Full showcase API response."""

    videos: list[VideoShowcaseItem]
    stats: ShowcaseStats


class FeaturedConfig(BaseModel):
    """Configuration for a featured video."""

    folder: str
    video: str
    display_order: int = 0
    carousel_title: Optional[str] = None


class ShowcaseConfig(BaseModel):
    """Showcase configuration file structure."""

    version: str = "1.0"
    featured: list[FeaturedConfig] = []
    settings: dict = {"max_carousel_items": 6, "default_sort": "newest"}


def load_showcase_config() -> ShowcaseConfig:
    """Load featured videos configuration from JSON file."""
    config_path = OUTPUT_DIR / "showcase-config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                data = json.load(f)
                return ShowcaseConfig(**data)
        except Exception:
            pass
    return ShowcaseConfig()


def scan_showcase_videos() -> ShowcaseResponse:
    """Scan output directory and build video showcase data."""
    config = load_showcase_config()

    # Build lookup for featured videos: (folder, video) -> FeaturedConfig
    featured_lookup = {(f.folder, f.video): f for f in config.featured}

    videos = []
    brands: set[str] = set()
    freepik_count = 0
    veo3_count = 0
    product_folders: set[str] = set()

    if not OUTPUT_DIR.exists():
        return ShowcaseResponse(
            videos=[],
            stats=ShowcaseStats(
                total_videos=0,
                total_products=0,
                total_brands=0,
                freepik_count=0,
                veo3_count=0,
            ),
        )

    for folder in OUTPUT_DIR.iterdir():
        if not folder.is_dir():
            continue

        readme_path = folder / "README.md"
        if not readme_path.exists():
            continue

        parsed = parse_readme(readme_path)
        if not parsed:
            continue

        product_folders.add(folder.name)
        if parsed.brand:
            brands.add(parsed.brand)

        # Find all video files in folder
        for video_file in folder.glob("*.mp4"):
            filename = video_file.name

            # Determine provider from filename prefix
            if filename.startswith("freepik_"):
                provider = "freepik"
                task_id = filename[8:-4]  # Remove "freepik_" and ".mp4"
                freepik_count += 1
            elif filename.startswith("veo3_"):
                provider = "veo3"
                task_id = filename[5:-4]  # Remove "veo3_" and ".mp4"
                veo3_count += 1
            else:
                continue  # Skip unknown video formats

            # Check if featured
            featured_key = (folder.name, filename)
            featured_config = featured_lookup.get(featured_key)

            video_item = VideoShowcaseItem(
                folder_name=folder.name,
                video_path=f"/output/{folder.name}/{filename}",
                provider=provider,
                task_id=task_id,
                product=ProductShowcaseMetadata(
                    title=parsed.title,
                    brand=parsed.brand,
                    price=parsed.price,
                    description=parsed.description,
                    product_url=parsed.product_url,
                ),
                prompt=parsed.video_prompt,
                generated_at=parsed.generated_at,
                is_featured=featured_config is not None,
                featured_order=featured_config.display_order if featured_config else None,
                carousel_title=featured_config.carousel_title if featured_config else None,
            )
            videos.append(video_item)

    # Sort by generated_at descending (newest first)
    videos.sort(key=lambda v: v.generated_at or "", reverse=True)

    stats = ShowcaseStats(
        total_videos=len(videos),
        total_products=len(product_folders),
        total_brands=len(brands),
        freepik_count=freepik_count,
        veo3_count=veo3_count,
    )

    return ShowcaseResponse(videos=videos, stats=stats)


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

    def add_log(self, job_id: str, source: str, message: str) -> None:
        """Add a log entry to a job."""
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.logs.append(LogEntry(
                    timestamp=datetime.utcnow(),
                    source=source,
                    message=message,
                ))
                # Keep only the last 50 logs
                if len(job.logs) > 50:
                    job.logs = job.logs[-50:]

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
        # Initialize with research agent active
        job_store.update(
            job_id,
            stage=JobStage.EXTRACTING_METADATA,
            progress_percent=5,
            message="Starting generation...",
            agents=AgentStatuses(research=AgentStatus.ACTIVE),
        )
        job_store.add_log(job_id, "System", "Starting ad generation pipeline")

        def on_log(source: str, message: str) -> None:
            """Callback to add log entries."""
            job_store.add_log(job_id, source, message)
            # Also print to console
            print(f"[{source}] {message}")

        def on_tool_call(name: str, args: dict) -> None:
            """Callback to update job status based on tool calls."""
            if name == "get_product_metadata":
                job_store.update(
                    job_id,
                    stage=JobStage.EXTRACTING_METADATA,
                    progress_percent=10,
                    message="Extracting product metadata...",
                    agents=AgentStatuses(research=AgentStatus.ACTIVE),
                )
                job_store.add_log(job_id, "Agent", "Calling get_product_metadata tool")
            elif name == "generate_video":
                job_store.update(
                    job_id,
                    stage=JobStage.GENERATING_VIDEO,
                    progress_percent=50,
                    message="Generating video...",
                    video_prompt=args.get("prompt"),
                    agents=AgentStatuses(
                        research=AgentStatus.DONE,
                        content=AgentStatus.DONE,
                        video=AgentStatus.ACTIVE,
                    ),
                )
                job_store.add_log(job_id, "Agent", "Starting video generation")

        def on_tool_result(name: str, args: dict, result: any) -> None:
            """Callback to update job status with tool results."""
            if name == "get_product_metadata":
                job_store.update(
                    job_id,
                    stage=JobStage.GENERATING_PROMPT,
                    progress_percent=35,
                    message="Creating video prompt...",
                    product=result,
                    agents=AgentStatuses(
                        research=AgentStatus.DONE,
                        content=AgentStatus.ACTIVE,
                    ),
                )
                product_title = result.get("title", "Unknown product")
                job_store.add_log(job_id, "Agent", f"Extracted metadata for: {product_title}")

        # Create output directory for this job
        job_output_dir = OUTPUT_DIR / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        # Create and run the agent with log callback
        agent = AdGeneratorAgent(
            output_dir=job_output_dir,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
            on_log=on_log,
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
            agents=AgentStatuses(
                research=AgentStatus.DONE,
                content=AgentStatus.DONE,
                video=AgentStatus.DONE,
            ),
        )
        job_store.add_log(job_id, "System", "Ad generation completed successfully")

    except Exception as e:
        job_store.update(
            job_id,
            stage=JobStage.FAILED,
            progress_percent=0,
            message="Generation failed",
            error=str(e),
            agents=AgentStatuses(
                research=AgentStatus.FAILED,
                content=AgentStatus.FAILED,
                video=AgentStatus.FAILED,
            ),
        )
        job_store.add_log(job_id, "System", f"Error: {str(e)}")


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


# Showcase API endpoints
@app.get("/api/showcase/videos", response_model=ShowcaseResponse)
async def get_showcase_videos():
    """Get all videos for the showcase, with metadata from output directory."""
    return scan_showcase_videos()


@app.get("/api/showcase/featured", response_model=list[VideoShowcaseItem])
async def get_featured_videos():
    """Get only featured videos for README carousel."""
    showcase = scan_showcase_videos()
    featured = [v for v in showcase.videos if v.is_featured]
    featured.sort(key=lambda v: v.featured_order or 999)
    return featured


@app.get("/api/showcase/config", response_model=ShowcaseConfig)
async def get_showcase_config():
    """Get current showcase configuration."""
    return load_showcase_config()


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


@app.get("/video-showcase.html")
async def video_showcase():
    """Serve the video showcase HTML."""
    showcase_path = _PROJECT_ROOT / "video-showcase.html"
    if showcase_path.exists():
        return FileResponse(str(showcase_path))
    raise HTTPException(status_code=404, detail="Video showcase not found")


# Mount static files after the root route
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Mount output directory for video files
output_path = _PROJECT_ROOT / "output"
if output_path.exists():
    app.mount("/output", StaticFiles(directory=str(output_path)), name="output")


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

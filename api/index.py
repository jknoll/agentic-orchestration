"""FastAPI serverless function for AdFlow API."""

import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    url: str


@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "AdFlow API running"}


@app.get("/api/jobs")
async def list_jobs():
    # In serverless, jobs won't persist between invocations
    return []


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    # In serverless, we can't share state between functions
    # Return a demo response indicating the limitation
    return {
        "job_id": job_id,
        "stage": "demo",
        "progress_percent": 100,
        "message": "Demo mode - Run locally for full functionality",
        "agents": {
            "research": "standby",
            "content": "standby",
            "video": "standby"
        },
        "logs": [
            {"timestamp": "2024-01-01T00:00:00", "source": "System", "message": "Serverless demo mode"}
        ]
    }


@app.post("/api/generate")
async def generate(request: GenerateRequest):
    job_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    job = {
        "job_id": job_id,
        "product_url": request.url,
        "stage": "demo",
        "progress_percent": 0,
        "message": "Demo mode - Full generation requires local server",
        "created_at": now,
        "updated_at": now,
        "error": "Vercel serverless has timeout limits. Run locally for full video generation.",
        "product": None,
        "video_prompt": None,
        "video_path": None,
        "agents": {
            "research": "standby",
            "content": "standby",
            "video": "standby"
        },
        "logs": [
            {"timestamp": now, "source": "System", "message": "Job created (demo mode)"},
            {"timestamp": now, "source": "System", "message": "Full generation requires local server"}
        ]
    }

    return {"job_id": job_id, "status": "queued", "job": job}

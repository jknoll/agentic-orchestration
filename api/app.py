"""FastAPI serverless function for AdFlow API."""

import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store
jobs = {}


class GenerateRequest(BaseModel):
    url: str


class JobResponse(BaseModel):
    job_id: str
    status: str


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "AdFlow API running"}


@app.get("/api/jobs")
def list_jobs():
    return list(jobs.values())


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    if job_id in jobs:
        return jobs[job_id]
    raise HTTPException(status_code=404, detail="Job not found")


@app.post("/api/generate")
def generate(request: GenerateRequest):
    job_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    jobs[job_id] = {
        "job_id": job_id,
        "product_url": request.url,
        "stage": "failed",
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

    return {"job_id": job_id, "status": "queued"}

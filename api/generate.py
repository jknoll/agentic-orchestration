"""Generate endpoint."""

import json
import uuid
from datetime import datetime


def handler(request):
    """Handle POST /api/generate."""
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
            "body": ""
        }

    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    try:
        body = json.loads(request.body) if request.body else {}
        url = body.get("url", "")
    except (json.JSONDecodeError, AttributeError):
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Invalid JSON body"})
        }

    job_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    # In demo mode, return a job that shows the limitation
    job = {
        "job_id": job_id,
        "product_url": url,
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

    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps({"job_id": job_id, "status": "queued", "job": job})
    }

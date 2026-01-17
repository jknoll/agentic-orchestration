"""Status endpoint with dynamic job_id."""

import json


def handler(request):
    """Handle GET /api/status/{job_id}."""
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    # Handle CORS preflight
    if request.method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": ""
        }

    # Extract job_id from the path
    # Path will be like /api/status/abc123
    path_parts = request.path.split("/")
    job_id = path_parts[-1] if path_parts else None

    if not job_id:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Missing job_id"})
        }

    # In serverless, we can't share state between functions
    # Return a demo response indicating the limitation
    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps({
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
        })
    }

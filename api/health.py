"""Health check endpoint."""

import json


def handler(request):
    """Handle GET /api/health."""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps({"status": "ok", "message": "AdFlow API running"})
    }

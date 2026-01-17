"""List jobs endpoint."""

import json

# Shared in-memory job store (note: won't persist across function invocations in serverless)
jobs = {}


def handler(request):
    """Handle GET /api/jobs."""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps(list(jobs.values()))
    }

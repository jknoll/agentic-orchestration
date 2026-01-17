"""Status endpoint with dynamic job_id."""

from http.server import BaseHTTPRequestHandler
import json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Extract job_id from the path
        path_parts = self.path.split("/")
        job_id = path_parts[-1].split("?")[0] if path_parts else "unknown"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # In serverless, we can't share state between functions
        response = json.dumps({
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
        self.wfile.write(response.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

"""Generate endpoint."""

from http.server import BaseHTTPRequestHandler
import json
import uuid
from datetime import datetime


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read the request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"

        try:
            data = json.loads(body)
            url = data.get("url", "")
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON body"}).encode())
            return

        job_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow().isoformat()

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

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        response = json.dumps({"job_id": job_id, "status": "queued", "job": job})
        self.wfile.write(response.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

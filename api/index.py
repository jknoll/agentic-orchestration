"""Vercel serverless function handler for AdFlow API."""

import json
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

# In-memory job store
jobs = {}


class handler(BaseHTTPRequestHandler):
    """HTTP request handler for Vercel."""

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        path = urlparse(self.path).path

        if path == '/api/health':
            self._json_response({'status': 'ok', 'message': 'AdFlow API running'})
        elif path == '/api/jobs':
            self._json_response(list(jobs.values()))
        elif path.startswith('/api/status/'):
            job_id = path.split('/')[-1]
            if job_id in jobs:
                self._json_response(jobs[job_id])
            else:
                self._json_response({'error': 'Job not found'}, 404)
        else:
            self._json_response({'error': 'Not found'}, 404)

    def do_POST(self):
        """Handle POST requests."""
        path = urlparse(self.path).path

        if path == '/api/generate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body) if body else {}
                url = data.get('url')

                if not url:
                    self._json_response({'error': 'URL is required'}, 400)
                    return

                job_id = str(uuid.uuid4())[:8]
                now = datetime.utcnow().isoformat()

                jobs[job_id] = {
                    'job_id': job_id,
                    'product_url': url,
                    'stage': 'failed',
                    'progress_percent': 0,
                    'message': 'Demo mode - Full generation requires local server',
                    'created_at': now,
                    'updated_at': now,
                    'error': 'Vercel serverless has timeout limits. Run locally for full video generation.',
                    'product': None,
                    'video_prompt': None,
                    'video_path': None,
                    'agents': {
                        'research': 'standby',
                        'content': 'standby',
                        'video': 'standby'
                    },
                    'logs': [
                        {'timestamp': now, 'source': 'System', 'message': 'Job created (demo mode)'},
                        {'timestamp': now, 'source': 'System', 'message': 'Full generation requires local server'}
                    ]
                }

                self._json_response({'job_id': job_id, 'status': 'queued'})
            except json.JSONDecodeError:
                self._json_response({'error': 'Invalid JSON'}, 400)
        else:
            self._json_response({'error': 'Not found'}, 404)

    def _send_cors_headers(self):
        """Send CORS headers."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json_response(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

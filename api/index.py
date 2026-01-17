"""Vercel serverless function handler for AdFlow API."""

import os
import sys
import json
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add the src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# In-memory job store (note: serverless functions are stateless, so this resets)
jobs = {}


class handler(BaseHTTPRequestHandler):
    """HTTP request handler for Vercel."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/health':
            self._send_json({'status': 'ok', 'message': 'AdFlow API is running'})
        elif path == '/api/jobs':
            self._send_json(list(jobs.values()))
        elif path.startswith('/api/status/'):
            job_id = path.split('/')[-1]
            if job_id in jobs:
                self._send_json(jobs[job_id])
            else:
                self._send_error(404, 'Job not found')
        else:
            self._send_error(404, 'Not found')

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/generate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body)
                url = data.get('url')
                
                if not url:
                    self._send_error(400, 'URL is required')
                    return

                # Create a new job
                job_id = str(uuid.uuid4())[:8]
                now = datetime.utcnow().isoformat()

                jobs[job_id] = {
                    'job_id': job_id,
                    'product_url': url,
                    'stage': 'queued',
                    'progress_percent': 0,
                    'message': 'Job queued - Note: Video generation requires a persistent server',
                    'created_at': now,
                    'updated_at': now,
                    'error': 'Vercel serverless functions have timeout limits. For full video generation, please run locally or deploy to Railway/Render/Fly.io',
                    'agents': {
                        'research': 'standby',
                        'content': 'standby',
                        'video': 'standby'
                    },
                    'logs': [
                        {
                            'timestamp': now,
                            'source': 'System',
                            'message': 'Job created on Vercel (demo mode)'
                        },
                        {
                            'timestamp': now,
                            'source': 'System',
                            'message': 'Note: Full video generation requires a persistent server'
                        }
                    ]
                }

                self._send_json({
                    'job_id': job_id,
                    'status': 'queued',
                    'warning': 'Vercel has timeout limits. Video generation may not complete.'
                })
            except json.JSONDecodeError:
                self._send_error(400, 'Invalid JSON')
        else:
            self._send_error(404, 'Not found')

    def _set_cors_headers(self):
        """Set CORS headers."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _send_json(self, data, status=200):
        """Send a JSON response."""
        self.send_response(status)
        self._set_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, status, message):
        """Send an error response."""
        self._send_json({'error': message}, status)

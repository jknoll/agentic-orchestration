"""Vercel serverless function handler for AdFlow API using Flask."""

import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory job store (note: serverless functions are stateless, so this resets between calls)
jobs = {}


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'AdFlow API is running'})


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs."""
    return jsonify(list(jobs.values()))


@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """Get job status."""
    if job_id in jobs:
        return jsonify(jobs[job_id])
    return jsonify({'error': 'Job not found'}), 404


@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate():
    """Start a new generation job."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    try:
        data = request.get_json()
        url = data.get('url') if data else None

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Create a new job
        job_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow().isoformat()

        jobs[job_id] = {
            'job_id': job_id,
            'product_url': url,
            'stage': 'failed',
            'progress_percent': 0,
            'message': 'Demo mode - Video generation requires a persistent server',
            'created_at': now,
            'updated_at': now,
            'error': 'Vercel serverless functions have timeout limits. For full video generation, please run locally or deploy to Railway/Render/Fly.io',
            'product': None,
            'video_prompt': None,
            'video_path': None,
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

        return jsonify({
            'job_id': job_id,
            'status': 'queued'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.after_request
def add_cors_headers(response):
    """Add CORS headers to all responses."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response


# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=3000)

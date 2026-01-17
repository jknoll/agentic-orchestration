#!/bin/bash
# Start the AdFlow API server

PORT=${1:-8000}

echo "============================================"
echo "  ADFLOW API SERVER"
echo "============================================"
echo ""
echo "Starting server at http://localhost:$PORT"
echo "Press Ctrl+C to stop"
echo ""

source .venv/bin/activate
uvicorn ad_generator.api:app --reload --port $PORT

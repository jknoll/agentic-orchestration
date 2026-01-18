#!/bin/bash
# Start the AdFlow API server

PORT=${1:-8000}

echo "=================================="
echo "  ADFLOW API SERVER"
echo "=================================="
echo ""
echo "Starting server at http://localhost:$PORT"
echo "Press Ctrl+C to stop"
echo ""

# Use virtual environment if it exists
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
else
    PYTHON="python3"
fi

# Check if uvicorn is installed
if ! $PYTHON -c "import uvicorn" 2>/dev/null; then
    echo "Installing dependencies..."
    $PYTHON -m pip install -e .
fi

# Start the FastAPI server with uvicorn
$PYTHON -m uvicorn ad_generator.api:app --host 0.0.0.0 --port $PORT --reload

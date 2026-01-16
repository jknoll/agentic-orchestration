# Ad Generator

Generate video advertisements from product pages using Claude Agent SDK and FreePik's video generation API.

## Overview

This tool takes a product detail page URL as input and automatically:
1. Extracts product metadata (title, description, images, price, brand)
2. Uses Claude to craft a compelling ad script and video prompt
3. Generates a short video advertisement using FreePik's AI video generation

## Installation

### Prerequisites

- Python 3.10+
- Claude Code CLI (for authentication)
- FreePik API key

### Setup

1. Clone the repository:
```bash
git clone <repo-url>
cd agentic-orchestration
```

2. Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your FreePik API key
```

5. Authenticate Claude Code (if not already):
```bash
claude
# Follow the prompts to authenticate
```

## Usage

```bash
# Basic usage
ad-generator "https://example.com/product/123"

# Specify output directory
ad-generator "https://example.com/product/123" --output ./my-ads
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FREEPIK_API_KEY` | Yes | Your FreePik API key |
| `ANTHROPIC_API_KEY` | No | Anthropic API key (optional if using Claude Code auth) |

## Project Structure

```
src/ad_generator/
├── __init__.py
├── main.py              # CLI entry point
├── agent.py             # Claude Agent orchestration
├── metadata_extractor.py # Product page scraping
├── freepik_client.py    # FreePik API client
└── models.py            # Pydantic data models
```

## How It Works

1. **Metadata Extraction**: The tool fetches the product page and extracts structured data using:
   - JSON-LD (schema.org Product)
   - Open Graph meta tags
   - Standard HTML elements

2. **Claude Agent**: An AI agent analyzes the product and creates:
   - Ad concept and script
   - Optimized video generation prompt

3. **Video Generation**: The prompt is sent to FreePik's WAN 2.6 model to generate a 5-second video advertisement.

## Development

Install dev dependencies:
```bash
pip install -e ".[dev]"
```

Run tests:
```bash
pytest
```

## License

MIT

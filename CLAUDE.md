# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ad Generator is a Python CLI tool that creates video advertisements from product pages. It uses the Claude Agent SDK for AI orchestration and FreePik's WAN 2.6 API for video generation.

## Commands

```bash
# Install dependencies (use virtual environment)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"

# Run the CLI
ad-generator "https://example.com/product/123"
ad-generator "https://example.com/product/123" --output ./my-ads

# Run tests
pytest

# Run a single test
pytest tests/test_file.py::test_function_name
```

## Architecture

The system follows a three-stage pipeline:

1. **Metadata Extraction** (`metadata_extractor.py`): Fetches product pages and extracts structured data using JSON-LD (schema.org Product), Open Graph meta tags, or fallback HTML parsing.

2. **Agent Orchestration** (`agent.py`): `AdGeneratorAgent` uses the Claude Agent SDK to analyze products and generate video prompts. It creates an MCP server with two tools:
   - `get_product_metadata`: Wraps the metadata extractor
   - `generate_video`: Wraps the FreePik client

   The agent receives a system prompt defining its role as an ad copywriter/video director, then autonomously calls tools to complete the workflow.

3. **Video Generation** (`freepik_client.py`): `FreePikClient` handles async communication with FreePik's text-to-video API, including polling for completion and downloading results.

## Key Patterns

- **Claude Agent SDK integration**: Tools are defined using the `@tool` decorator and registered via `create_sdk_mcp_server()`. The agent uses `permission_mode="bypassPermissions"` for automated execution.

- **Async throughout**: All I/O operations (HTTP, file downloads) use `httpx.AsyncClient` and `anyio` for async execution.

- **Pydantic models** (`models.py`): All data structures use Pydantic for validation and serialization.

## Environment Variables

The credentials should be stored in the environment in an .env file, which should never be committed to github. An env.example can be committed and includes credential documentation.

## Working process and TODO.md
Work from the list of items in TODO.md as a default next action, or when directed to do so by the user.

Create a GitHub issue for each item you undertake in the TODO.md file, Link from the `TODO.md` to the GitHub issue. Work in a feature branch. When a TODO is complete, create a pull request for review. Update the TODO.md file to indicate that the TODO has been addressed and a pull request created. 

## Reviewing Frontend Changes

In order to review front-end changes, use the local web server and Claude for Chrome. 
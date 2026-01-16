# Refined PRD: Research Agent Feature

## Overview

Build a Research Agent that extracts product information from any product URL using the TinyFish (AgentQL) API. This implementation follows the existing patterns established by `AdGeneratorAgent`.

---

## Key Changes from Original PRD

| Original PRD | Refined Plan | Rationale |
|--------------|--------------|-----------|
| `tools/tinyfish_tool.py` separate file | Inline in `ResearchAgent._create_tools()` | Matches `AdGeneratorAgent` pattern |
| `agents/definitions.py` with `AgentDefinition` | `ResearchAgent` class | `AgentDefinition` doesn't exist in codebase |
| Root-level `tools/`, `agents/` dirs | Flat in `src/ad_generator/` | Consistency with existing layout |
| `query()` streaming API | `ClaudeSDKClient` context manager | Matches existing usage |
| Manual test script | pytest with respx mocks | Matches test infrastructure |

---

## File Structure

```
src/ad_generator/
├── __init__.py          # Update exports
├── main.py              # Extend CLI (optional)
├── agent.py             # Existing AdGeneratorAgent
├── research_agent.py    # NEW: ResearchAgent class
├── agentql_client.py    # NEW: AgentQL API client
├── models.py            # Add research models
├── metadata_extractor.py
└── freepik_client.py
```

---

## Implementation

### 1. Models (`models.py` additions)

```python
class ProductResearch(BaseModel):
    """Structured product research data from AgentQL."""
    product_name: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    features: list[str] = []
    specifications: list[str] = []
    benefits: list[str] = []
    target_audience: Optional[str] = None
    images: list[str] = []
    url: str


class MarketingAnalysis(BaseModel):
    """Marketing analysis derived from product research."""
    key_features: list[str] = []
    target_audience_description: str = ""
    pain_points_addressed: list[str] = []
    unique_selling_propositions: list[str] = []
    marketing_hooks: dict[str, str] = {}  # emotional, rational, social


class ResearchOutput(BaseModel):
    """Final output of research agent."""
    product: ProductResearch
    analysis: Optional[MarketingAnalysis] = None
    raw_response: Optional[str] = None
```

### 2. AgentQL Client (`agentql_client.py`)

Follow `FreePikClient` pattern:

```python
"""AgentQL API client for product extraction."""

import os
from typing import Optional

import httpx

from .models import ProductResearch


class AgentQLError(Exception):
    """AgentQL API error."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AgentQLClient:
    """Async client for AgentQL/TinyFish API."""

    ENDPOINT = "https://api.agentql.com/v1/query-data"

    DEFAULT_FIELDS = [
        "product_name", "price", "description",
        "features", "specifications", "benefits",
        "target_audience", "images"
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("AGENTQL_API_KEY")
        if not self.api_key:
            raise AgentQLError("AgentQL API key not provided")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    def _build_query(self, fields: list[str]) -> str:
        """Build AgentQL query from field list."""
        query_parts = []
        array_fields = {"features", "specifications", "benefits", "images"}
        for field in fields:
            if field in array_fields:
                query_parts.append(f"    {field}[]")
            else:
                query_parts.append(f"    {field}")
        return "{\n" + "\n".join(query_parts) + "\n}"

    async def extract_product(
        self,
        url: str,
        fields: Optional[list[str]] = None,
    ) -> ProductResearch:
        """Extract product data from URL."""
        if not self._client:
            raise AgentQLError("Client not initialized. Use 'async with' context.")

        fields = fields or self.DEFAULT_FIELDS
        query = self._build_query(fields)

        try:
            response = await self._client.post(
                self.ENDPOINT,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "url": url,
                    "query": query,
                    "is_scroll_to_bottom_enabled": True,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract nested data
            result_data = data.get("data", data)

            return ProductResearch(
                product_name=result_data.get("product_name"),
                price=result_data.get("price"),
                description=result_data.get("description"),
                features=result_data.get("features", []),
                specifications=result_data.get("specifications", []),
                benefits=result_data.get("benefits", []),
                target_audience=result_data.get("target_audience"),
                images=result_data.get("images", []),
                url=url,
            )
        except httpx.HTTPStatusError as e:
            raise AgentQLError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )
```

### 3. Research Agent (`research_agent.py`)

Follow `AdGeneratorAgent` pattern exactly:

```python
"""Research Agent for product analysis."""

import json
from typing import Any, Optional

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)

from .agentql_client import AgentQLClient, AgentQLError
from .models import ProductResearch, ResearchOutput


SYSTEM_PROMPT = """You are a product research specialist for marketing campaigns.

Your job is to extract comprehensive product information from product pages and analyze it for marketing purposes.

When given a product URL:
1. Use the extract_product tool to scrape the page
2. Analyze the extracted data thoroughly
3. Identify the target audience based on product features and positioning
4. Determine key pain points the product solves
5. Find unique selling propositions (USPs)

Return a structured summary in this format:

## Product Overview
- **Name**: [product name]
- **Price**: [price]
- **Category**: [inferred category]

## Key Features
1. [feature 1]
2. [feature 2]
(list top 5 most marketable features)

## Target Audience
[Description of ideal customer]

## Pain Points Addressed
- [pain point 1]
- [pain point 2]

## Unique Selling Propositions
- [USP 1]
- [USP 2]

## Marketing Hooks
- Emotional: [emotional appeal angle]
- Rational: [logical/practical appeal angle]
- Social: [social proof/status angle]

Be thorough but concise."""


class ResearchAgent:
    """Agent that extracts and analyzes product information."""

    def __init__(self, agentql_api_key: Optional[str] = None):
        self.agentql_api_key = agentql_api_key
        self._product_research: Optional[ProductResearch] = None

    def _create_tools(self):
        """Create MCP tools for the agent."""

        @tool(
            "extract_product",
            "Extract product information from a URL using AgentQL. Returns name, price, description, features, specifications, benefits, and images.",
            {"url": str, "fields": str},
        )
        async def extract_product(args: dict[str, Any]) -> dict:
            """Extract product data from URL."""
            try:
                url = args["url"]
                fields_str = args.get("fields", "")
                fields = [f.strip() for f in fields_str.split(",")] if fields_str else None

                async with AgentQLClient(api_key=self.agentql_api_key) as client:
                    research = await client.extract_product(url, fields)

                self._product_research = research

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(research.model_dump(), indent=2),
                        }
                    ]
                }
            except AgentQLError as e:
                return {
                    "content": [{"type": "text", "text": f"Extraction failed: {e}"}],
                    "isError": True,
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Unexpected error: {e}"}],
                    "isError": True,
                }

        return [extract_product]

    async def research_product(self, product_url: str) -> ResearchOutput:
        """Research a product and provide marketing analysis."""
        tools = self._create_tools()

        mcp_server = create_sdk_mcp_server(
            name="research-tools",
            version="1.0.0",
            tools=tools,
        )

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"research": mcp_server},
            allowed_tools=["mcp__research__extract_product"],
            permission_mode="bypassPermissions",
            max_turns=5,
        )

        prompt = f"""Research this product and provide a marketing analysis:
{product_url}

Use the extract_product tool to fetch the product information, then analyze it."""

        raw_response = ""

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            raw_response += block.text + "\n"
                            print(f"Agent: {block.text}")
                        elif isinstance(block, ToolUseBlock):
                            print(f"Using tool: {block.name}")
                elif isinstance(message, ResultMessage):
                    print(f"Completed: {message.subtype}")

        if not self._product_research:
            raise RuntimeError("Failed to extract product data")

        return ResearchOutput(
            product=self._product_research,
            raw_response=raw_response.strip(),
        )
```

### 4. CLI Extension (`main.py`)

Add research command:

```python
async def run_research(product_url: str, output_format: str) -> None:
    """Run the product research workflow."""
    from .research_agent import ResearchAgent

    print(f"Researching product: {product_url}")
    print("-" * 50)

    agent = ResearchAgent()
    result = await agent.research_product(product_url)

    if output_format == "json":
        print(json.dumps(result.model_dump(), indent=2))
    else:
        print("\n" + "=" * 50)
        print("RESEARCH COMPLETE")
        print("=" * 50)
        print(result.raw_response)


def cli() -> None:
    parser = argparse.ArgumentParser(...)
    subparsers = parser.add_subparsers(dest="command")

    # Generate command (existing)
    gen_parser = subparsers.add_parser("generate", help="Generate video ad")
    gen_parser.add_argument("url", help="Product URL")
    gen_parser.add_argument("-o", "--output", type=Path, default=Path("./output"))

    # Research command (new)
    res_parser = subparsers.add_parser("research", help="Research product")
    res_parser.add_argument("url", help="Product URL")
    res_parser.add_argument("--format", choices=["text", "json"], default="text")

    # Backward compatibility: if no subcommand, treat as generate
    args = parser.parse_args()
    load_dotenv()

    if args.command == "research":
        anyio.run(run_research, args.url, args.format)
    else:
        anyio.run(run_generator, args.url, getattr(args, 'output', Path("./output")))
```

---

## Environment Variables

```
AGENTQL_API_KEY=your_agentql_api_key   # Required for research
ANTHROPIC_API_KEY=your_anthropic_key   # Optional
FREEPIK_API_KEY=your_freepik_key       # Required for generate
```

---

## Testing (`tests/test_research_agent.py`)

```python
import pytest
import respx
from httpx import Response

from ad_generator.agentql_client import AgentQLClient, AgentQLError
from ad_generator.models import ProductResearch


MOCK_RESPONSE = {
    "data": {
        "product_name": "Test Product",
        "price": "$99.99",
        "description": "A great product",
        "features": ["Feature 1", "Feature 2"],
        "specifications": ["Spec 1"],
        "benefits": ["Benefit 1"],
        "target_audience": "Tech enthusiasts",
        "images": ["https://example.com/img.jpg"],
    }
}


class TestAgentQLClient:
    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_product_success(self):
        respx.post("https://api.agentql.com/v1/query-data").mock(
            return_value=Response(200, json=MOCK_RESPONSE)
        )

        async with AgentQLClient(api_key="test-key") as client:
            result = await client.extract_product("https://example.com/product")

        assert result.product_name == "Test Product"
        assert result.price == "$99.99"
        assert len(result.features) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_product_api_error(self):
        respx.post("https://api.agentql.com/v1/query-data").mock(
            return_value=Response(401, text="Unauthorized")
        )

        async with AgentQLClient(api_key="bad-key") as client:
            with pytest.raises(AgentQLError) as exc:
                await client.extract_product("https://example.com/product")
            assert exc.value.status_code == 401
```

---

## Verification

1. **Unit tests**: `pytest tests/test_research_agent.py`
2. **Manual test**:
   ```bash
   export AGENTQL_API_KEY="your_key"
   ad-generator research "https://amazon.com/dp/B0BSHF7WHW"
   ad-generator research "https://amazon.com/dp/B0BSHF7WHW" --format json
   ```

---

## Acceptance Criteria

- [ ] `agentql_client.py` implements async client with context manager pattern
- [ ] `research_agent.py` follows `AdGeneratorAgent` class structure
- [ ] Tool uses `@tool` decorator with correct signature
- [ ] Tool returns `{"content": [{"type": "text", "text": "..."}]}` format
- [ ] MCP server created via `create_sdk_mcp_server()`
- [ ] Agent uses `ClaudeSDKClient` with `ClaudeAgentOptions`
- [ ] CLI extended with `research` subcommand
- [ ] Tests use pytest-asyncio and respx mocks
- [ ] Error handling with custom `AgentQLError` exception

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
                fields = (
                    [f.strip() for f in fields_str.split(",") if f.strip()]
                    if fields_str
                    else None
                )

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

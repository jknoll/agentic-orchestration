"""Claude Agent for ad generation orchestration."""

import json
from pathlib import Path
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

from .freepik_client import FreePikClient, FreePikError
from .metadata_extractor import extract_product_metadata
from .models import (
    GenerationOutput,
    ProductMetadata,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoResolution,
)
from .yutori_client import YutoriClient, YutoriError


SYSTEM_PROMPT = """You are an expert advertising copywriter and video director specializing in short-form video ads for e-commerce products.

Your task is to create compelling video advertisements by:
1. Analyzing product information to understand its key selling points
2. Crafting a persuasive video script optimized for short attention spans
3. Writing an effective video generation prompt that captures the essence of the ad

When creating video prompts, follow these guidelines:
- Keep it under 8 seconds total
- Start with a hook that grabs attention in the first 2 seconds
- Highlight the product's main benefit or unique value proposition
- End with a clear call-to-action
- Use vivid, cinematic descriptions for the video prompt
- Describe camera movements, lighting, and mood
- Focus on showing the product in an aspirational context

You have access to tools to:
1. Fetch product metadata from a URL
2. Generate a video using the description you create

Always use the tools provided. First fetch the product info, then generate the video with your crafted prompt."""


class AdGeneratorAgent:
    """Agent that orchestrates ad video generation."""

    def __init__(
        self,
        output_dir: Path = Path("./output"),
        freepik_api_key: Optional[str] = None,
    ):
        """
        Initialize the ad generator agent.

        Args:
            output_dir: Directory to save generated videos
            freepik_api_key: FreePik API key (or uses FREEPIK_API_KEY env var)
        """
        self.output_dir = output_dir
        self.freepik_api_key = freepik_api_key
        self._product_metadata: Optional[ProductMetadata] = None
        self._video_result: Optional[VideoGenerationResult] = None
        self._video_prompt: Optional[str] = None

    def _create_tools(self):
        """Create MCP tools for the agent."""

        @tool(
            "get_product_metadata",
            "Fetch product information from a URL. Returns title, description, images, price, and brand.",
            {"url": str},
        )
        async def get_product_metadata(args: dict[str, Any]) -> dict:
            """Fetch product metadata from URL."""
            try:
                url = args["url"]
                metadata = await extract_product_metadata(url)
                self._product_metadata = metadata
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(metadata.model_dump(), indent=2),
                        }
                    ]
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Error fetching metadata: {e}"}],
                    "isError": True,
                }

        @tool(
            "generate_video",
            "Generate a video advertisement using the provided prompt. The prompt should describe the video scene, including visuals, camera movement, and mood.",
            {"prompt": str, "resolution": str},
        )
        async def generate_video(args: dict[str, Any]) -> dict:
            """Generate video from prompt."""
            try:
                prompt = args["prompt"]
                resolution_str = args.get("resolution", "720p")
                resolution = (
                    VideoResolution.FHD_1080P
                    if "1080" in resolution_str
                    else VideoResolution.HD_720P
                )

                self._video_prompt = prompt

                request = VideoGenerationRequest(
                    prompt=prompt,
                    resolution=resolution,
                    with_audio=True,
                )

                async with FreePikClient(api_key=self.freepik_api_key) as client:
                    # Submit generation request
                    result = await client.generate_video(request)

                    # Wait for completion
                    result = await client.wait_for_completion(
                        result.task_id,
                        resolution=resolution,
                        timeout_seconds=300,
                    )

                    # Download if successful
                    if result.video_url:
                        self.output_dir.mkdir(parents=True, exist_ok=True)
                        output_path = self.output_dir / f"ad_{result.task_id}.mp4"
                        await client.download_video(result.video_url, output_path)
                        result = VideoGenerationResult(
                            task_id=result.task_id,
                            status=result.status,
                            video_url=str(output_path),
                        )

                    self._video_result = result

                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Video generated successfully!\nTask ID: {result.task_id}\nStatus: {result.status.value}\nSaved to: {result.video_url}",
                            }
                        ]
                    }
            except FreePikError as e:
                return {
                    "content": [{"type": "text", "text": f"Video generation failed: {e}"}],
                    "isError": True,
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Unexpected error: {e}"}],
                    "isError": True,
                }

        @tool(
            "research_product",
            "Research a product to get detailed information including features, pricing, reviews, and target audience. Use this when you need comprehensive product data from the web.",
            {"product_name": str},
        )
        async def research_product(args: dict[str, Any]) -> dict:
            """Research product information using Yutori API."""
            try:
                product_name = args["product_name"]
                async with YutoriClient() as client:
                    result = await client.research_product(product_name)
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result.model_dump(), indent=2),
                            }
                        ]
                    }
            except YutoriError as e:
                return {
                    "content": [{"type": "text", "text": f"Research failed: {e}"}],
                    "isError": True,
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Unexpected error: {e}"}],
                    "isError": True,
                }

        return [get_product_metadata, generate_video, research_product]

    async def generate_ad(self, product_url: str) -> GenerationOutput:
        """
        Generate a video ad for the given product URL.

        Args:
            product_url: URL of the product detail page

        Returns:
            GenerationOutput with all generation artifacts
        """
        tools = self._create_tools()

        # Create MCP server with our tools
        mcp_server = create_sdk_mcp_server(
            name="ad-generator-tools",
            version="1.0.0",
            tools=tools,
        )

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"ad_tools": mcp_server},
            allowed_tools=[
                "mcp__ad_tools__get_product_metadata",
                "mcp__ad_tools__generate_video",
                "mcp__ad_tools__research_product",
            ],
            permission_mode="bypassPermissions",
            max_turns=10,
        )

        prompt = f"""Create a short video advertisement for the product at this URL: {product_url}

Steps:
1. First, use the get_product_metadata tool to fetch information about the product
2. Based on the product info, craft a compelling video prompt that will create an engaging 5-8 second ad
3. Use the generate_video tool with your crafted prompt to create the ad

Focus on making the ad visually compelling and emotionally engaging while highlighting the product's key benefits."""

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(f"Agent: {block.text}")
                        elif isinstance(block, ToolUseBlock):
                            print(f"Using tool: {block.name}")
                elif isinstance(message, ResultMessage):
                    print(f"Completed: {message.subtype}")

        # Compile results
        if not self._product_metadata:
            raise RuntimeError("Failed to extract product metadata")
        if not self._video_result:
            raise RuntimeError("Failed to generate video")

        from .models import AdScript, AdScene

        # Create a simple script representation
        script = AdScript(
            product_name=self._product_metadata.title,
            hook="Discover something amazing",
            scenes=[
                AdScene(
                    description="Product showcase",
                    duration_seconds=5.0,
                    visual_notes=self._video_prompt,
                )
            ],
            call_to_action="Shop now",
        )

        return GenerationOutput(
            product=self._product_metadata,
            script=script,
            video_prompt=self._video_prompt or "",
            video_result=self._video_result,
            output_path=self._video_result.video_url,
        )

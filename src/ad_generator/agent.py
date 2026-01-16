"""Claude Agent for ad generation orchestration."""

import json
from pathlib import Path
from typing import Any, Callable, Optional

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
from .kie_client import KieAIClient, KieAIError
from .metadata_extractor import extract_product_metadata
from .models import (
    AdScene,
    AdScript,
    GenerationOutput,
    ProductMetadata,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoProvider,
    VideoResolution,
    VideoStatus,
)


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
- Keep the prompt under 500 characters for optimal video generation

IMPORTANT: After crafting your video prompt, you MUST call the generate_video tool with your prompt. The video generation happens automatically - you just need to provide the prompt text.

You have access to tools to:
1. Fetch product metadata from a URL (get_product_metadata)
2. Generate a video using the description you create (generate_video)

Workflow:
1. First, call get_product_metadata with the product URL
2. Analyze the product information returned
3. Craft a compelling video prompt (describe it in your response)
4. Call generate_video with your crafted prompt

Always use the tools provided and complete all steps."""


class AdGeneratorAgent:
    """Agent that orchestrates ad video generation."""

    def __init__(
        self,
        output_dir: Path = Path("./output"),
        freepik_api_key: Optional[str] = None,
        use_veo3: bool = False,
        veo3_quality: bool = False,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        Initialize the ad generator agent.

        Args:
            output_dir: Directory to save generated videos
            freepik_api_key: FreePik API key (or uses FREEPIK_API_KEY env var)
            use_veo3: Whether to also generate video using Kie.ai Veo 3
            veo3_quality: Use Veo 3 Quality mode instead of Fast (slower, higher quality)
            on_tool_call: Callback for tool call notifications (tool_name, args)
        """
        self.output_dir = output_dir
        self.freepik_api_key = freepik_api_key
        self.use_veo3 = use_veo3
        self.veo3_quality = veo3_quality
        self.on_tool_call = on_tool_call
        self._product_metadata: Optional[ProductMetadata] = None
        self._video_results: list[VideoGenerationResult] = []
        self._video_prompt: Optional[str] = None

    def _log_tool_call(self, tool_name: str, args: dict):
        """Log a tool call with its arguments."""
        if self.on_tool_call:
            self.on_tool_call(tool_name, args)

    def _create_tools(self):
        """Create MCP tools for the agent."""

        @tool(
            "get_product_metadata",
            "Fetch product information from a URL. Returns title, description, images, price, and brand.",
            {"url": str},
        )
        async def get_product_metadata(args: dict[str, Any]) -> dict:
            """Fetch product metadata from URL."""
            self._log_tool_call("get_product_metadata", args)
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
                # Create fallback metadata from URL
                from urllib.parse import urlparse, unquote
                parsed = urlparse(url)
                # Extract product name from URL path
                path_parts = [p for p in parsed.path.split("/") if p]
                product_slug = path_parts[-1] if path_parts else "product"
                # Convert slug to readable name
                product_name = unquote(product_slug).replace("-", " ").replace("_", " ").title()

                self._product_metadata = ProductMetadata(
                    url=url,
                    title=product_name,
                    description=None,
                    images=[],
                    price=None,
                    brand=parsed.netloc.replace("www.", "").split(".")[0].title(),
                )
                return {
                    "content": [{"type": "text", "text": f"Error fetching metadata: {e}. Using fallback data from URL: {product_name}"}],
                    "isError": True,
                }

        @tool(
            "generate_video",
            "Generate a video advertisement using the provided prompt. The prompt should describe the video scene, including visuals, camera movement, and mood. Keep prompts under 500 characters.",
            {"prompt": str},
        )
        async def generate_video(args: dict[str, Any]) -> dict:
            """Generate video from prompt using configured providers."""
            self._log_tool_call("generate_video", args)
            try:
                prompt = args["prompt"]
                self._video_prompt = prompt

                results = []
                errors = []

                # Generate with FreePik (WAN 2.6)
                try:
                    print("\n[FreePik WAN 2.6] Submitting video generation request...")
                    result = await self._generate_freepik(prompt)
                    results.append(result)
                    print(f"[FreePik WAN 2.6] Video generated: {result.local_path}")
                except FreePikError as e:
                    errors.append(f"FreePik: {e}")
                    print(f"[FreePik WAN 2.6] Error: {e}")

                # Generate with Kie.ai (Veo 3) if enabled
                if self.use_veo3:
                    mode = "Quality" if self.veo3_quality else "Fast"
                    try:
                        print(f"\n[Kie.ai Veo 3 {mode}] Submitting video generation request...")
                        result = await self._generate_kie(prompt)
                        results.append(result)
                        print(f"[Kie.ai Veo 3 {mode}] Video generated: {result.local_path}")
                    except KieAIError as e:
                        errors.append(f"Kie.ai: {e}")
                        print(f"[Kie.ai Veo 3 {mode}] Error: {e}")

                self._video_results = results

                if not results:
                    return {
                        "content": [{"type": "text", "text": f"All video generations failed: {'; '.join(errors)}"}],
                        "isError": True,
                    }

                # Build success message
                lines = ["Video generation completed!"]
                for r in results:
                    if r.provider == VideoProvider.FREEPIK:
                        provider_name = "FreePik WAN 2.6"
                    else:
                        veo3_mode = "Quality" if self.veo3_quality else "Fast"
                        provider_name = f"Kie.ai Veo 3 {veo3_mode}"
                    lines.append(f"\n{provider_name}:")
                    lines.append(f"  Task ID: {r.task_id}")
                    lines.append(f"  Status: {r.status.value}")
                    if r.local_path:
                        lines.append(f"  Saved to: {r.local_path}")

                if errors:
                    lines.append(f"\nWarnings: {'; '.join(errors)}")

                return {
                    "content": [{"type": "text", "text": "\n".join(lines)}]
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Unexpected error: {e}"}],
                    "isError": True,
                }

        return [get_product_metadata, generate_video]

    async def _generate_freepik(self, prompt: str) -> VideoGenerationResult:
        """Generate video using FreePik API."""
        request = VideoGenerationRequest(
            prompt=prompt,
            resolution=VideoResolution.HD_720P,
            with_audio=True,
        )

        async with FreePikClient(api_key=self.freepik_api_key) as client:
            result = await client.generate_video(request)

            result = await client.wait_for_completion(
                result.task_id,
                resolution=request.resolution,
                timeout_seconds=300,
            )

            local_path = None
            if result.video_url:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                output_path = self.output_dir / f"freepik_{result.task_id}.mp4"
                await client.download_video(result.video_url, output_path)
                local_path = str(output_path)

            return VideoGenerationResult(
                task_id=result.task_id,
                status=result.status,
                provider=VideoProvider.FREEPIK,
                video_url=result.video_url,
                local_path=local_path,
            )

    async def _generate_kie(self, prompt: str) -> VideoGenerationResult:
        """Generate video using Kie.ai Veo 3."""
        request = VideoGenerationRequest(
            prompt=prompt,
            resolution=VideoResolution.HD_720P,
            with_audio=True,
        )

        # Use Fast mode by default, Quality mode if explicitly requested
        use_fast = not self.veo3_quality
        async with KieAIClient(use_fast=use_fast) as client:
            result = await client.generate_video(request)

            result = await client.wait_for_completion(
                result.task_id,
                timeout_seconds=600,
            )

            local_path = None
            if result.video_url:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                output_path = self.output_dir / f"veo3_{result.task_id}.mp4"
                await client.download_video(result.video_url, output_path)
                local_path = str(output_path)

            return VideoGenerationResult(
                task_id=result.task_id,
                status=VideoStatus.COMPLETED if result.video_url else VideoStatus.FAILED,
                provider=VideoProvider.KIE_AI,
                video_url=result.video_url,
                local_path=local_path,
            )

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
                            print(f"\nAgent: {block.text}")
                        elif isinstance(block, ToolUseBlock):
                            # Tool calls are logged via on_tool_call callback
                            pass
                elif isinstance(message, ResultMessage):
                    print(f"\nCompleted: {message.subtype}")

        # Compile results
        if not self._product_metadata:
            raise RuntimeError("Failed to extract product metadata")
        if not self._video_results:
            raise RuntimeError("Failed to generate any videos")

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
            video_results=self._video_results,
            output_dir=str(self.output_dir),
        )

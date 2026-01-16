"""CLI entry point for the ad generator."""

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import anyio
from dotenv import load_dotenv

from .agent import AdGeneratorAgent
from .models import GenerationOutput, VideoProvider

# Project root directory (where pyproject.toml lives)
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"


def url_to_dirname(url: str) -> str:
    """Convert a URL to a filesystem-safe directory name."""
    parsed = urlparse(url)
    # Combine host and path
    path_part = parsed.path.strip("/").replace("/", "_")
    if not path_part:
        path_part = "root"
    dir_name = f"{parsed.netloc}_{path_part}"
    # Remove or replace unsafe characters
    dir_name = re.sub(r'[<>:"/\\|?*]', '_', dir_name)
    # Truncate if too long (keep it reasonable for filesystems)
    if len(dir_name) > 200:
        # Use hash suffix to ensure uniqueness
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        dir_name = dir_name[:190] + "_" + url_hash
    return dir_name


def create_output_directory(base_dir: Path, product_url: str) -> Path:
    """Create an output directory named after the product URL."""
    dir_name = url_to_dirname(product_url)
    output_dir = base_dir / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_readme(output_dir: Path, result: GenerationOutput, veo3_quality: bool = False) -> None:
    """Write a README.md file documenting the generation."""
    lines = [
        f"# Ad Generation: {result.product.title}",
        "",
        "## Input",
        "",
        f"**Product URL:** {result.product.url}",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## Product Information",
        "",
        f"- **Title:** {result.product.title}",
    ]

    if result.product.brand:
        lines.append(f"- **Brand:** {result.product.brand}")
    if result.product.price:
        lines.append(f"- **Price:** {result.product.price}")
    if result.product.description:
        lines.append(f"- **Description:** {result.product.description[:200]}...")

    lines.extend([
        "",
        "## Video Prompt",
        "",
        "```",
        result.video_prompt,
        "```",
        "",
        "## Generated Videos",
        "",
    ])

    for video in result.video_results:
        if video.provider == VideoProvider.FREEPIK:
            provider_name = "FreePik WAN 2.6"
        else:
            veo3_mode = "Quality" if veo3_quality else "Fast"
            provider_name = f"Kie.ai Veo 3 {veo3_mode}"
        lines.append(f"### {provider_name}")
        lines.append("")
        lines.append(f"- **Task ID:** {video.task_id}")
        lines.append(f"- **Status:** {video.status.value}")
        if video.local_path:
            # Use relative path in README
            rel_path = Path(video.local_path).name
            lines.append(f"- **File:** [{rel_path}](./{rel_path})")
        lines.append("")

    readme_path = output_dir / "README.md"
    readme_path.write_text("\n".join(lines))


def write_prompt(output_dir: Path, prompt: str) -> None:
    """Write the video generation prompt to prompt.md."""
    prompt_path = output_dir / "prompt.md"
    prompt_path.write_text(prompt)


def print_tool_call(tool_name: str, args: dict) -> None:
    """Print a tool call with its arguments."""
    print(f"\n{'='*60}")
    print(f"TOOL CALL: {tool_name}")
    print(f"{'='*60}")
    for key, value in args.items():
        # Truncate long values
        str_value = str(value)
        if len(str_value) > 200:
            str_value = str_value[:200] + "..."
        print(f"  {key}: {str_value}")
    print()


async def run_generator(
    product_url: str,
    base_output_dir: Path,
    use_veo3: bool = False,
    veo3_quality: bool = False,
    force: bool = False,
) -> None:
    """Run the ad generation workflow."""
    print(f"{'='*60}")
    print("AD VIDEO GENERATOR")
    print(f"{'='*60}")
    print(f"\nProduct URL: {product_url}")
    print(f"Output directory: {base_output_dir}")
    if use_veo3:
        mode = "Quality" if veo3_quality else "Fast"
        print(f"Veo 3 (Kie.ai): Enabled ({mode} mode)")
    else:
        print(f"Veo 3 (Kie.ai): Disabled")
    print()

    # Create output directory based on URL
    output_dir = create_output_directory(base_output_dir, product_url)

    # Check for existing generation
    if not force:
        readme_path = output_dir / "README.md"
        if readme_path.exists():
            print(f"\n[WARNING] Generation already exists for this URL!")
            print(f"  Existing directory: {output_dir}")
            print(f"  Use --force to regenerate")
            sys.exit(0)

    agent = AdGeneratorAgent(
        output_dir=output_dir,
        use_veo3=use_veo3,
        veo3_quality=veo3_quality,
        on_tool_call=print_tool_call,
    )

    try:
        result = await agent.generate_ad(product_url)

        # Update output_dir in result
        result.output_dir = str(output_dir)

        # Write README and prompt
        write_readme(output_dir, result, veo3_quality)
        write_prompt(output_dir, result.video_prompt)

        # Print summary
        print("\n" + "="*60)
        print("GENERATION COMPLETE")
        print("="*60)
        print(f"\nProduct: {result.product.title}")
        if result.product.brand:
            print(f"Brand: {result.product.brand}")
        if result.product.price:
            print(f"Price: {result.product.price}")

        print(f"\n{'='*60}")
        print("VIDEO PROMPT")
        print(f"{'='*60}")
        print(result.video_prompt)

        print(f"\n{'='*60}")
        print("GENERATED VIDEOS")
        print(f"{'='*60}")
        for video in result.video_results:
            if video.provider == VideoProvider.FREEPIK:
                provider_name = "FreePik WAN 2.6"
            else:
                veo3_mode = "Quality" if veo3_quality else "Fast"
                provider_name = f"Kie.ai Veo 3 {veo3_mode}"
            print(f"\n{provider_name}:")
            print(f"  Status: {video.status.value}")
            print(f"  Task ID: {video.task_id}")
            if video.local_path:
                print(f"  File: {video.local_path}")

        print(f"\n{'='*60}")
        print(f"Output directory: {output_dir}")
        print(f"{'='*60}")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


def cli() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate video advertisements from product pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ad-generator "https://example.com/product/123"
  ad-generator "https://amazon.com/dp/B0..." --veo3
  ad-generator "https://example.com/product" --output ./my-ads --force

Environment Variables:
  FREEPIK_API_KEY       FreePik API key for WAN 2.6 video generation
  ANTHROPIC_API_KEY     Anthropic API key (optional if using Claude Code auth)
  KIE_API_KEY           Kie.ai API key (required for --veo3)
        """,
    )
    parser.add_argument(
        "url",
        help="URL of the product detail page",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory for generated videos (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--veo3",
        action="store_true",
        help="Also generate video using Kie.ai Veo 3 Fast (requires KIE_API_KEY)",
    )
    parser.add_argument(
        "--veo3-quality",
        action="store_true",
        help="Use Veo 3 Quality mode instead of Fast (slower, higher quality, $2 vs $0.40)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if output already exists for this URL",
    )

    args = parser.parse_args()

    # Convert CLI args to enums
    duration = VideoDuration(args.duration)
    resolution = VideoResolution.FHD_1080P if args.resolution == "1080p" else VideoResolution.HD_720P
    aspect_ratio = AspectRatio.PORTRAIT_9_16 if args.aspect_ratio == "9:16" else AspectRatio.LANDSCAPE_16_9

    # Load environment variables
    load_dotenv()

    # Run the generator
    anyio.run(
        run_generator,
        args.url,
        args.output,
        args.veo3,
        args.veo3_quality,
        args.force,
    )


if __name__ == "__main__":
    cli()

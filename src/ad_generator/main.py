"""CLI entry point for the ad generator."""

import argparse
import sys
from pathlib import Path

import anyio
from dotenv import load_dotenv

from .agent import AdGeneratorAgent


async def run_generator(product_url: str, output_dir: Path) -> None:
    """Run the ad generation workflow."""
    print(f"Generating ad for: {product_url}")
    print(f"Output directory: {output_dir}")
    print("-" * 50)

    agent = AdGeneratorAgent(output_dir=output_dir)

    try:
        result = await agent.generate_ad(product_url)

        print("\n" + "=" * 50)
        print("AD GENERATION COMPLETE")
        print("=" * 50)
        print(f"\nProduct: {result.product.title}")
        if result.product.brand:
            print(f"Brand: {result.product.brand}")
        if result.product.price:
            print(f"Price: {result.product.price}")
        print(f"\nVideo Prompt Used:")
        print(f"  {result.video_prompt}")
        print(f"\nVideo Status: {result.video_result.status.value}")
        print(f"Video Task ID: {result.video_result.task_id}")
        if result.output_path:
            print(f"\nVideo saved to: {result.output_path}")
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
  ad-generator "https://amazon.com/dp/B0..." --output ./my-ads

Environment Variables:
  FREEPIK_API_KEY    FreePik API key for video generation
  ANTHROPIC_API_KEY  Anthropic API key (optional if using Claude Code auth)
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
        default=Path("./output"),
        help="Output directory for generated videos (default: ./output)",
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Run the generator
    anyio.run(run_generator, args.url, args.output)


if __name__ == "__main__":
    cli()

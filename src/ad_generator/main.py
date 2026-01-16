"""CLI entry point for the ad generator."""

import argparse
import json
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


async def run_research(product_url: str, output_format: str) -> None:
    """Run the product research workflow."""
    from .research_agent import ResearchAgent

    print(f"Researching product: {product_url}")
    print("-" * 50)

    agent = ResearchAgent()

    try:
        result = await agent.research_product(product_url)

        if output_format == "json":
            print(json.dumps(result.model_dump(), indent=2))
        else:
            print("\n" + "=" * 50)
            print("RESEARCH COMPLETE")
            print("=" * 50)
            print(result.raw_response)
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
  ad-generator generate "https://example.com/product/123"
  ad-generator generate "https://amazon.com/dp/B0..." --output ./my-ads
  ad-generator research "https://amazon.com/dp/B0..."
  ad-generator research "https://amazon.com/dp/B0..." --format json

  # Backward compatible (defaults to generate):
  ad-generator "https://example.com/product/123"

Environment Variables:
  FREEPIK_API_KEY    FreePik API key for video generation
  AGENTQL_API_KEY    AgentQL API key for product research
  ANTHROPIC_API_KEY  Anthropic API key (optional if using Claude Code auth)
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate video ad")
    gen_parser.add_argument(
        "url",
        help="URL of the product detail page",
    )
    gen_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("./output"),
        help="Output directory for generated videos (default: ./output)",
    )

    # Research command
    res_parser = subparsers.add_parser("research", help="Research product")
    res_parser.add_argument(
        "url",
        help="URL of the product detail page",
    )
    res_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # For backward compatibility: allow URL as first positional arg without subcommand
    parser.add_argument(
        "url",
        nargs="?",
        help="URL of the product detail page (backward compatible mode)",
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

    # Determine which mode to run
    if args.command == "research":
        anyio.run(run_research, args.url, args.format)
    elif args.command == "generate":
        anyio.run(run_generator, args.url, args.output)
    elif args.url:
        # Backward compatibility: if no subcommand but URL provided, treat as generate
        anyio.run(run_generator, args.url, args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()

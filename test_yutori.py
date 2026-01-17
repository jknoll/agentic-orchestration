"""Quick test script for Yutori Research API."""

import asyncio
import json
import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_research():
    """Test the Yutori research_product function."""
    from ad_generator.yutori_client import YutoriClient, YutoriError

    # Check API key
    if not os.environ.get("YUTORI_API_KEY"):
        print("Error: YUTORI_API_KEY not set in .env file")
        return

    product_name = "MacBook Air M5"
    print(f"Researching: {product_name}")
    print("-" * 50)

    try:
        async with YutoriClient() as client:
            # Create task
            print("Creating research task...")
            task = await client.create_research_task(product_name)
            print(f"Task ID: {task.task_id}")
            print(f"Status: {task.status.value}")
            if task.view_url:
                print(f"View URL: {task.view_url}")

            # Wait for completion
            print("\nWaiting for research to complete (this may take 30-120 seconds)...")
            response = await client.wait_for_completion(
                task.task_id,
                timeout_seconds=180,
                poll_interval=5.0,
            )

            if response.result:
                print("\n" + "=" * 50)
                print("RESEARCH COMPLETE")
                print("=" * 50)
                print(json.dumps(response.result.model_dump(), indent=2))
            else:
                print("No result returned")

    except YutoriError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_research())

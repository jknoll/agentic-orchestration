"""Parser for output directory README.md files to extract showcase metadata."""

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class ParsedVideo(BaseModel):
    """Video information parsed from README.md."""

    provider: str  # "freepik" or "veo3"
    task_id: str
    status: str
    filename: str


class ParsedReadme(BaseModel):
    """Parsed content from a product output README.md."""

    title: str
    product_url: Optional[str] = None
    generated_at: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    video_prompt: Optional[str] = None
    videos: list[ParsedVideo] = []


def parse_readme(readme_path: Path) -> Optional[ParsedReadme]:
    """Parse a README.md file to extract product and video metadata.

    Args:
        readme_path: Path to the README.md file

    Returns:
        ParsedReadme object with extracted data, or None if parsing fails
    """
    if not readme_path.exists():
        return None

    try:
        content = readme_path.read_text()
    except Exception:
        return None

    # Extract title from H1: "# Ad Generation: {title}"
    title_match = re.search(r"^# Ad Generation: (.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Unknown Product"

    # Extract Product URL from: "**Product URL:** https://..."
    url_match = re.search(r"\*\*Product URL:\*\* (.+)$", content, re.MULTILINE)
    product_url = url_match.group(1).strip() if url_match else None

    # Extract Generated timestamp: "**Generated:** 2026-01-16T16:42:22.069084"
    generated_match = re.search(r"\*\*Generated:\*\* (.+)$", content, re.MULTILINE)
    generated_at = generated_match.group(1).strip() if generated_match else None

    # Extract Product Information section
    # Pattern: "- **Title:** ..." (skip this, we have it from H1)
    # Pattern: "- **Brand:** Pioneer DJ"
    brand_match = re.search(r"- \*\*Brand:\*\* (.+)$", content, re.MULTILINE)
    brand = brand_match.group(1).strip() if brand_match else None

    # Pattern: "- **Price:** $349"
    price_match = re.search(r"- \*\*Price:\*\* (.+)$", content, re.MULTILINE)
    price = price_match.group(1).strip() if price_match else None

    # Pattern: "- **Description:** ..."
    desc_match = re.search(r"- \*\*Description:\*\* (.+?)(?=\n\n|\n##|\Z)", content, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else None
    # Clean up description - remove extra whitespace
    if description:
        description = " ".join(description.split())

    # Extract Video Prompt from code block
    prompt_match = re.search(r"## Video Prompt\n\n```\n(.+?)\n```", content, re.DOTALL)
    video_prompt = prompt_match.group(1).strip() if prompt_match else None

    # Extract video entries from Generated Videos section
    videos = []

    # Find FreePik videos: "### FreePik WAN 2.6" section
    freepik_section = re.search(
        r"### FreePik.*?\n\n- \*\*Task ID:\*\* (.+?)\n- \*\*Status:\*\* (.+?)\n- \*\*File:\*\* \[(.+?)\]",
        content,
        re.DOTALL,
    )
    if freepik_section:
        videos.append(
            ParsedVideo(
                provider="freepik",
                task_id=freepik_section.group(1).strip(),
                status=freepik_section.group(2).strip(),
                filename=freepik_section.group(3).strip(),
            )
        )

    # Find Kie.ai/Veo3 videos: "### Kie.ai Veo 3" section
    veo3_section = re.search(
        r"### Kie\.ai.*?\n\n- \*\*Task ID:\*\* (.+?)\n- \*\*Status:\*\* (.+?)\n- \*\*File:\*\* \[(.+?)\]",
        content,
        re.DOTALL,
    )
    if veo3_section:
        videos.append(
            ParsedVideo(
                provider="veo3",
                task_id=veo3_section.group(1).strip(),
                status=veo3_section.group(2).strip(),
                filename=veo3_section.group(3).strip(),
            )
        )

    return ParsedReadme(
        title=title,
        product_url=product_url,
        generated_at=generated_at,
        brand=brand,
        price=price,
        description=description,
        video_prompt=video_prompt,
        videos=videos,
    )


def scan_output_videos(output_dir: Path) -> list[tuple[Path, ParsedReadme]]:
    """Scan output directory for all product folders with README.md files.

    Args:
        output_dir: Path to the output directory

    Returns:
        List of (folder_path, parsed_readme) tuples
    """
    results = []

    if not output_dir.exists():
        return results

    for folder in output_dir.iterdir():
        if not folder.is_dir():
            continue

        readme_path = folder / "README.md"
        if not readme_path.exists():
            continue

        parsed = parse_readme(readme_path)
        if parsed:
            results.append((folder, parsed))

    # Sort by generated_at descending (newest first)
    results.sort(key=lambda x: x[1].generated_at or "", reverse=True)

    return results

"""Extract product metadata from web pages."""

import asyncio
import json
import os
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .models import ProductMetadata
from .tinyfish_client import TinyFishClient, TinyFishError


async def extract_product_metadata(url: str) -> ProductMetadata:
    """
    Extract product metadata from a URL using multiple strategies.

    Runs both TinyFish AI extraction and HTML parsing, then merges results.
    TinyFish data is preferred when available.
    """
    # Start HTML extraction
    html_task = asyncio.create_task(_extract_via_html(url))

    # Try TinyFish extraction if API key is available
    tinyfish_data = None
    if os.environ.get("MINO_API_KEY"):
        try:
            print("[TinyFish] Starting AI-powered metadata extraction...")
            tinyfish_data = await _extract_via_tinyfish(url)
            print("[TinyFish] Extraction complete")
        except TinyFishError as e:
            print(f"[TinyFish] Extraction failed: {e}")
        except Exception as e:
            print(f"[TinyFish] Unexpected error: {e}")

    # Wait for HTML extraction
    html_metadata = await html_task

    # Merge results, preferring TinyFish data
    return _merge_metadata(html_metadata, tinyfish_data, url)


async def _extract_via_tinyfish(url: str) -> Optional[dict]:
    """Extract metadata using TinyFish AI."""
    async with TinyFishClient() as client:
        return await client.extract_product_metadata(url)


async def _extract_via_html(url: str) -> ProductMetadata:
    """
    Extract product metadata from HTML using multiple strategies.

    Tries extraction in order of reliability:
    1. JSON-LD structured data (schema.org Product)
    2. Open Graph meta tags
    3. Standard meta tags
    4. Fallback to page content
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "lxml")

        # Try JSON-LD first
        metadata = _extract_from_json_ld(soup, url)
        if metadata and metadata.title:
            return metadata

        # Try Open Graph
        metadata = _extract_from_open_graph(soup, url)
        if metadata and metadata.title:
            return metadata

        # Fallback to generic extraction
        return _extract_fallback(soup, url)

    except Exception as e:
        print(f"[HTML] Extraction failed: {e}")
        # Return empty metadata on failure
        return ProductMetadata(
            title="",
            description=None,
            images=[],
            price=None,
            brand=None,
            features=[],
            url=url,
        )


def _merge_metadata(
    html_metadata: ProductMetadata,
    tinyfish_data: Optional[dict],
    url: str,
) -> ProductMetadata:
    """
    Merge metadata from HTML and TinyFish sources.

    TinyFish data is preferred when available and non-empty.
    Lists (images, features) are combined with unique values.
    """
    if tinyfish_data is None:
        return html_metadata

    # Helper to get non-empty value, preferring TinyFish
    def prefer_tinyfish(tf_value: Any, html_value: Any) -> Any:
        if tf_value is not None and tf_value != "" and tf_value != []:
            return tf_value
        return html_value

    # Extract TinyFish values (handle both dict and potential nested structure)
    tf_title = tinyfish_data.get("title", "")
    tf_description = tinyfish_data.get("description")
    tf_price = tinyfish_data.get("price")
    tf_brand = tinyfish_data.get("brand")
    tf_images = tinyfish_data.get("images", [])
    tf_features = tinyfish_data.get("features", [])

    # Ensure lists are actually lists
    if not isinstance(tf_images, list):
        tf_images = [tf_images] if tf_images else []
    if not isinstance(tf_features, list):
        tf_features = [tf_features] if tf_features else []

    # Merge images (combine unique URLs)
    merged_images = []
    seen_images = set()
    for img in tf_images + html_metadata.images:
        if img and img not in seen_images:
            merged_images.append(img)
            seen_images.add(img)

    # Merge features (combine unique)
    merged_features = []
    seen_features = set()
    for feature in tf_features + html_metadata.features:
        if feature and feature not in seen_features:
            merged_features.append(feature)
            seen_features.add(feature)

    return ProductMetadata(
        title=prefer_tinyfish(tf_title, html_metadata.title) or "Unknown Product",
        description=prefer_tinyfish(tf_description, html_metadata.description),
        images=merged_images,
        price=prefer_tinyfish(tf_price, html_metadata.price),
        brand=prefer_tinyfish(tf_brand, html_metadata.brand),
        features=merged_features,
        url=url,
    )


def _extract_from_json_ld(soup: BeautifulSoup, url: str) -> Optional[ProductMetadata]:
    """Extract metadata from JSON-LD structured data."""
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string or "")

            # Handle @graph structure
            if isinstance(data, dict) and "@graph" in data:
                data = data["@graph"]

            # Handle list of items
            if isinstance(data, list):
                for item in data:
                    if _is_product_schema(item):
                        return _parse_product_schema(item, url)
            elif _is_product_schema(data):
                return _parse_product_schema(data, url)
        except (json.JSONDecodeError, TypeError):
            continue

    return None


def _is_product_schema(data: Any) -> bool:
    """Check if data is a Product schema."""
    if not isinstance(data, dict):
        return False
    schema_type = data.get("@type", "")
    if isinstance(schema_type, list):
        return "Product" in schema_type
    return schema_type == "Product"


def _parse_product_schema(data: dict, url: str) -> ProductMetadata:
    """Parse a Product schema into ProductMetadata."""
    images = []
    image_data = data.get("image", [])
    if isinstance(image_data, str):
        images = [image_data]
    elif isinstance(image_data, list):
        for img in image_data:
            if isinstance(img, str):
                images.append(img)
            elif isinstance(img, dict):
                images.append(img.get("url", img.get("contentUrl", "")))

    price = None
    offers = data.get("offers", {})
    if isinstance(offers, dict):
        price = offers.get("price")
        if price:
            currency = offers.get("priceCurrency", "")
            price = f"{currency} {price}".strip()
    elif isinstance(offers, list) and offers:
        first_offer = offers[0]
        price = first_offer.get("price")
        if price:
            currency = first_offer.get("priceCurrency", "")
            price = f"{currency} {price}".strip()

    brand = None
    brand_data = data.get("brand", {})
    if isinstance(brand_data, dict):
        brand = brand_data.get("name")
    elif isinstance(brand_data, str):
        brand = brand_data

    return ProductMetadata(
        title=data.get("name", ""),
        description=data.get("description"),
        images=[img for img in images if img],
        price=price,
        brand=brand,
        features=[],
        url=url,
    )


def _extract_from_open_graph(soup: BeautifulSoup, url: str) -> Optional[ProductMetadata]:
    """Extract metadata from Open Graph meta tags."""
    og_title = soup.find("meta", property="og:title")
    if not og_title:
        return None

    title = og_title.get("content", "")
    if not title:
        return None

    og_description = soup.find("meta", property="og:description")
    description = og_description.get("content") if og_description else None

    images = []
    for og_image in soup.find_all("meta", property="og:image"):
        img_url = og_image.get("content")
        if img_url:
            images.append(urljoin(url, img_url))

    og_price = soup.find("meta", property="product:price:amount")
    og_currency = soup.find("meta", property="product:price:currency")
    price = None
    if og_price:
        amount = og_price.get("content", "")
        currency = og_currency.get("content", "") if og_currency else ""
        price = f"{currency} {amount}".strip()

    og_brand = soup.find("meta", property="product:brand")
    brand = og_brand.get("content") if og_brand else None

    return ProductMetadata(
        title=title,
        description=description,
        images=images,
        price=price,
        brand=brand,
        features=[],
        url=url,
    )


def _extract_fallback(soup: BeautifulSoup, url: str) -> ProductMetadata:
    """Fallback extraction from page content."""
    # Title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True)
        if h1_text and len(h1_text) < len(title):
            title = h1_text

    # Description
    description = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content")

    # Images - find large images
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue

        # Skip small images, icons, logos
        if any(skip in src.lower() for skip in ["icon", "logo", "sprite", "pixel"]):
            continue

        # Check for size hints
        width = img.get("width", "")
        height = img.get("height", "")
        try:
            if width and int(width) < 200:
                continue
            if height and int(height) < 200:
                continue
        except ValueError:
            pass

        images.append(urljoin(url, src))

    return ProductMetadata(
        title=title,
        description=description,
        images=images[:5],  # Limit to first 5 images
        price=None,
        brand=None,
        features=[],
        url=url,
    )

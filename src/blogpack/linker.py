"""Rewrite links to work locally between downloaded posts."""

import re
from pathlib import Path
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup


def rewrite_links(
    html: str,
    base_url: str,
    post_slugs: set[str],
    image_map: dict[str, Path] | None = None,
    relative_image_path: str = "images",
) -> str:
    """
    Rewrite internal blog links to local relative links.

    Args:
        html: The HTML content to process
        base_url: The blog's base URL (e.g., "https://www.cold-takes.com/")
        post_slugs: Set of all known post slugs
        image_map: Optional dict mapping image URLs to local paths
        relative_image_path: Relative path to images folder

    Returns:
        HTML with rewritten links
    """
    soup = BeautifulSoup(html, "lxml")
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc

    # Rewrite anchor links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        parsed = urlparse(href)

        # Check if this is an internal link to the same domain
        if parsed.netloc == "" or parsed.netloc == base_domain:
            # Extract the path
            path = parsed.path.strip("/")

            # Check if this path matches a known post slug
            if path in post_slugs:
                a["href"] = f"{path}.html"

    # Rewrite image sources
    if image_map:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and src in image_map:
                local_path = image_map[src]
                img["src"] = f"{relative_image_path}/{local_path.name}"
                if "data-src" in img.attrs:
                    del img["data-src"]

    # Extract just the body content (lxml adds html/body wrapper)
    body = soup.find("body")
    if body:
        return "".join(str(child) for child in body.children)
    return str(soup)


def extract_slug_from_url(url: str, base_url: str) -> str:
    """Extract the post slug from a full URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    return path if path else "index"


def get_all_slugs(articles) -> set[str]:
    """Get set of all post slugs from articles."""
    return {article.slug for article in articles}

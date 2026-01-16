"""Crawl blog to discover all posts."""

import httpx
from rich.console import Console

from .platforms import detect_platform, BlogPlatform, PLATFORMS
from .platforms.base import PostInfo

console = Console()


async def discover_posts(base_url: str, platform: BlogPlatform | None = None) -> tuple[BlogPlatform, list[PostInfo]]:
    """
    Discover all posts on a blog.

    Args:
        base_url: The blog's base URL
        platform: Optional platform override (auto-detects if None)

    Returns:
        Tuple of (detected platform, list of post info)
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "blogpack/0.1.0 (offline reader)"}
    ) as client:
        # Fetch homepage to detect platform
        if platform is None:
            console.print(f"[dim]Fetching {base_url} to detect platform...[/dim]")
            response = await client.get(base_url)
            response.raise_for_status()

            platform = detect_platform(response.text)
            if platform is None:
                raise ValueError(
                    f"Could not detect blog platform. Supported platforms: "
                    f"{', '.join(p.name for p in PLATFORMS)}"
                )

        console.print(f"[green]Detected platform: {platform.name}[/green]")

        # Get all post URLs using platform-specific method
        console.print("[dim]Discovering posts...[/dim]")
        posts = await platform.get_post_urls(base_url, client)
        console.print(f"[green]Found {len(posts)} posts[/green]")

        return platform, posts

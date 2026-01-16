"""Download blog posts and images."""

import asyncio
import hashlib
import random
from pathlib import Path
from urllib.parse import urlparse, urljoin

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .platforms.base import BlogPlatform, Article, PostInfo

console = Console()

# Rate limiting defaults
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_REQUEST_DELAY = 0.1  # seconds between requests

# Platform-specific rate limits (more conservative for Substack)
PLATFORM_RATE_LIMITS = {
    "substack": {"max_concurrent": 2, "request_delay": 1.0},
    "ghost": {"max_concurrent": 5, "request_delay": 0.1},
    "wordpress": {"max_concurrent": 3, "request_delay": 0.5},
}

# Retry settings for 429 errors
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0  # seconds


async def download_posts(
    base_url: str,
    posts: list[PostInfo],
    platform: BlogPlatform,
    include_images: bool = True,
    output_dir: Path | None = None,
) -> tuple[list[Article], dict[str, Path]]:
    """
    Download all posts and their images.

    Args:
        base_url: Blog base URL
        posts: List of posts to download
        platform: The blog platform handler
        include_images: Whether to download images
        output_dir: Directory to save images (if include_images is True)

    Returns:
        Tuple of (list of Article objects, dict mapping image URL to local path)
    """
    # Get platform-specific rate limits
    rate_limits = PLATFORM_RATE_LIMITS.get(
        platform.name,
        {"max_concurrent": DEFAULT_MAX_CONCURRENT, "request_delay": DEFAULT_REQUEST_DELAY}
    )
    max_concurrent = rate_limits["max_concurrent"]
    request_delay = rate_limits["request_delay"]

    console.print(f"[dim]Using rate limits for {platform.name}: {max_concurrent} concurrent, {request_delay}s delay[/dim]")

    articles = []
    image_map: dict[str, Path] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "blogpack/0.1.0 (offline reader)"}
    ) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            # Download posts
            task = progress.add_task("[cyan]Downloading posts...", total=len(posts))

            skipped_count = 0

            async def download_post(post: PostInfo) -> Article | None:
                nonlocal skipped_count
                async with semaphore:
                    retries = 0
                    backoff = INITIAL_BACKOFF
                    while retries <= MAX_RETRIES:
                        try:
                            await asyncio.sleep(request_delay)
                            response = await client.get(post.url)

                            # Handle 429 Too Many Requests with exponential backoff
                            if response.status_code == 429:
                                retries += 1
                                if retries > MAX_RETRIES:
                                    console.print(f"[yellow]Warning: Max retries reached for {post.url}[/yellow]")
                                    progress.advance(task)
                                    return None
                                # Add jitter to backoff
                                jitter = random.uniform(0.5, 1.5)
                                wait_time = backoff * jitter
                                console.print(f"[yellow]Rate limited, waiting {wait_time:.1f}s before retry...[/yellow]")
                                await asyncio.sleep(wait_time)
                                backoff *= 2  # Exponential backoff
                                continue

                            response.raise_for_status()
                            article = platform.extract_article(response.text, post.url)
                            if article is None:
                                skipped_count += 1
                            progress.advance(task)
                            return article
                        except httpx.HTTPStatusError as e:
                            if e.response.status_code == 429:
                                retries += 1
                                if retries > MAX_RETRIES:
                                    console.print(f"[yellow]Warning: Max retries reached for {post.url}[/yellow]")
                                    progress.advance(task)
                                    return None
                                jitter = random.uniform(0.5, 1.5)
                                wait_time = backoff * jitter
                                console.print(f"[yellow]Rate limited, waiting {wait_time:.1f}s before retry...[/yellow]")
                                await asyncio.sleep(wait_time)
                                backoff *= 2
                                continue
                            console.print(f"[yellow]Warning: Failed to download {post.url}: {e}[/yellow]")
                            progress.advance(task)
                            return None
                        except Exception as e:
                            console.print(f"[yellow]Warning: Failed to download {post.url}: {e}[/yellow]")
                            progress.advance(task)
                            return None
                    return None

            results = await asyncio.gather(*[download_post(p) for p in posts])
            articles = [a for a in results if a is not None]

            if skipped_count > 0:
                console.print(f"[yellow]Skipped {skipped_count} premium/paywalled posts[/yellow]")

            # Download images if requested
            if include_images and output_dir:
                all_images = set()
                for article in articles:
                    all_images.update(article.image_urls)

                if all_images:
                    images_dir = output_dir / "images"
                    images_dir.mkdir(parents=True, exist_ok=True)

                    img_task = progress.add_task("[cyan]Downloading images...", total=len(all_images))

                    async def download_image(url: str) -> tuple[str, Path | None]:
                        async with semaphore:
                            retries = 0
                            backoff = INITIAL_BACKOFF
                            while retries <= MAX_RETRIES:
                                try:
                                    await asyncio.sleep(request_delay)
                                    response = await client.get(url)

                                    # Handle 429 with backoff
                                    if response.status_code == 429:
                                        retries += 1
                                        if retries > MAX_RETRIES:
                                            progress.advance(img_task)
                                            return url, None
                                        wait_time = backoff * random.uniform(0.5, 1.5)
                                        await asyncio.sleep(wait_time)
                                        backoff *= 2
                                        continue

                                    response.raise_for_status()

                                    # Generate filename from URL and content hash
                                    parsed = urlparse(url)
                                    ext = Path(parsed.path).suffix or ".jpg"
                                    content_hash = hashlib.md5(response.content).hexdigest()[:8]
                                    filename = f"{content_hash}{ext}"
                                    filepath = images_dir / filename

                                    filepath.write_bytes(response.content)
                                    progress.advance(img_task)
                                    return url, filepath
                                except Exception as e:
                                    console.print(f"[yellow]Warning: Failed to download image {url}: {e}[/yellow]")
                                    progress.advance(img_task)
                                    return url, None
                            return url, None

                    img_results = await asyncio.gather(*[download_image(url) for url in all_images])
                    image_map = {url: path for url, path in img_results if path is not None}

    return articles, image_map

"""Download blog posts and images."""

import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urlparse, urljoin

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .platforms.base import BlogPlatform, Article, PostInfo

console = Console()

# Rate limiting
MAX_CONCURRENT = 5
REQUEST_DELAY = 0.1  # seconds between requests


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
    articles = []
    image_map: dict[str, Path] = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

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

            async def download_post(post: PostInfo) -> Article | None:
                async with semaphore:
                    try:
                        await asyncio.sleep(REQUEST_DELAY)
                        response = await client.get(post.url)
                        response.raise_for_status()
                        article = platform.extract_article(response.text, post.url)
                        progress.advance(task)
                        return article
                    except Exception as e:
                        console.print(f"[yellow]Warning: Failed to download {post.url}: {e}[/yellow]")
                        progress.advance(task)
                        return None

            results = await asyncio.gather(*[download_post(p) for p in posts])
            articles = [a for a in results if a is not None]

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
                            try:
                                await asyncio.sleep(REQUEST_DELAY)
                                response = await client.get(url)
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

                    img_results = await asyncio.gather(*[download_image(url) for url in all_images])
                    image_map = {url: path for url, path in img_results if path is not None}

    return articles, image_map

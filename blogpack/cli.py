"""CLI entry point for blogpack."""

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console

from .crawler import discover_posts
from .downloader import download_posts
from .exporters import export_html, export_epub, export_pdf

app = typer.Typer(
    name="blogpack",
    help="Download entire blogs for offline reading with working internal links.",
    add_completion=False,
)
console = Console()


@app.command()
def main(
    url: str = typer.Argument(..., help="Blog URL to download"),
    output: Path = typer.Option(
        Path("./output"),
        "-o", "--output",
        help="Output directory",
    ),
    format: str = typer.Option(
        "all",
        "-f", "--format",
        help="Output format: all, epub, html, pdf, or comma-separated list",
    ),
    images: bool = typer.Option(
        True,
        "--images/--no-images",
        help="Download images (default: yes)",
    ),
    platform: str = typer.Option(
        None,
        "-p", "--platform",
        help="Force platform (ghost). Auto-detects if not specified.",
    ),
    limit: int = typer.Option(
        None,
        "-n", "--limit",
        help="Limit number of posts to download (useful for testing)",
    ),
):
    """
    Download a blog for offline reading.

    Example:
        blogpack https://www.cold-takes.com/ -o ./cold-takes
    """
    asyncio.run(_run(url, output, format, images, platform, limit))


async def _run(
    url: str,
    output: Path,
    format: str,
    images: bool,
    platform: str | None,
    limit: int | None,
):
    """Async main function."""
    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    url = url.rstrip("/") + "/"

    console.print(f"\n[bold]blogpack[/bold] - Downloading {url}\n")

    # Discover posts
    try:
        detected_platform, posts = await discover_posts(url, platform=None)
    except Exception as e:
        console.print(f"[red]Error discovering posts: {e}[/red]")
        raise typer.Exit(1)

    if not posts:
        console.print("[yellow]No posts found.[/yellow]")
        raise typer.Exit(0)

    # Apply limit if specified
    if limit and limit > 0:
        posts = posts[:limit]
        console.print(f"[cyan]Limiting to {limit} posts for download[/cyan]")

    # Download posts and images
    articles, image_map = await download_posts(
        base_url=url,
        posts=posts,
        platform=detected_platform,
        include_images=images,
        output_dir=output / "html" if images else None,
    )

    if not articles:
        console.print("[yellow]No articles could be downloaded.[/yellow]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Downloaded {len(articles)} articles[/bold]\n")

    # Determine blog title and author from first article
    parsed_url = urlparse(url)
    blog_title = parsed_url.netloc.replace("www.", "").replace(".com", "").replace(".org", "").title()
    blog_title = f"{blog_title} Archive"

    # Use most common author
    authors = [a.author for a in articles if a.author != "Unknown"]
    blog_author = max(set(authors), key=authors.count) if authors else "Unknown"

    # Parse formats
    formats = set()
    if format == "all":
        formats = {"html", "epub", "pdf"}
    else:
        formats = {f.strip().lower() for f in format.split(",")}

    # Export to requested formats
    if "html" in formats:
        export_html(
            articles=articles,
            output_dir=output,
            base_url=url,
            image_map=image_map if images else None,
            blog_title=blog_title,
        )

    if "epub" in formats:
        export_epub(
            articles=articles,
            output_dir=output,
            base_url=url,
            image_map=image_map if images else None,
            blog_title=blog_title,
            blog_author=blog_author,
        )

    if "pdf" in formats:
        export_pdf(
            articles=articles,
            output_dir=output,
            base_url=url,
            image_map=image_map if images else None,
            blog_title=blog_title,
            blog_author=blog_author,
        )

    console.print(f"\n[bold green]Done![/bold green] Output saved to {output.absolute()}\n")


if __name__ == "__main__":
    app()

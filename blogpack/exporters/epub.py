"""Export blog to EPUB format."""

from pathlib import Path
from datetime import datetime

from ebooklib import epub
from rich.console import Console

from ..platforms.base import Article
from ..cleaner import clean_html, READER_CSS
from ..linker import rewrite_links, get_all_slugs

console = Console()


def export_epub(
    articles: list[Article],
    output_dir: Path,
    base_url: str,
    image_map: dict[str, Path] | None = None,
    blog_title: str = "Blog Archive",
    blog_author: str = "Unknown",
) -> Path:
    """
    Export articles to EPUB format.

    Args:
        articles: List of Article objects
        output_dir: Output directory
        base_url: Original blog URL
        image_map: Dict mapping image URLs to local paths
        blog_title: Book title
        blog_author: Book author

    Returns:
        Path to the generated EPUB file
    """
    console.print(f"[dim]Generating EPUB with {len(articles)} chapters...[/dim]")

    book = epub.EpubBook()

    # Set metadata
    book.set_identifier(f"blogpack-{base_url}")
    book.set_title(blog_title)
    book.set_language("en")
    book.add_author(blog_author)
    book.add_metadata("DC", "date", datetime.now().isoformat())

    # Add CSS
    css = epub.EpubItem(
        uid="style",
        file_name="style.css",
        media_type="text/css",
        content=READER_CSS,
    )
    book.add_item(css)

    # Sort articles by date (oldest first for reading order)
    sorted_articles = sorted(
        articles,
        key=lambda a: a.date or datetime.min,
    )

    post_slugs = get_all_slugs(articles)
    chapters = []
    image_items = {}

    # Add images to epub first
    if image_map:
        for url, local_path in image_map.items():
            if local_path.exists():
                # Determine media type
                ext = local_path.suffix.lower()
                media_types = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                    ".svg": "image/svg+xml",
                }
                media_type = media_types.get(ext, "image/jpeg")

                img_item = epub.EpubItem(
                    uid=f"img_{local_path.stem}",
                    file_name=f"images/{local_path.name}",
                    media_type=media_type,
                    content=local_path.read_bytes(),
                )
                book.add_item(img_item)
                image_items[url] = f"images/{local_path.name}"

    # Create chapters
    for i, article in enumerate(sorted_articles):
        date_str = article.date.strftime("%B %d, %Y") if article.date else ""

        # Clean content and rewrite links
        content = clean_html(article.content_html)

        # Rewrite links for epub (internal links to other chapters)
        content = rewrite_links(
            content,
            base_url,
            post_slugs,
            image_map,
            relative_image_path="images",
        )

        # Also rewrite image paths for epub
        if image_items:
            for url, epub_path in image_items.items():
                content = content.replace(f'src="images/{Path(image_map[url]).name}"', f'src="{epub_path}"')

        # Create chapter HTML
        chapter_html = f"""
<html>
<head>
    <title>{article.title}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <h1>{article.title}</h1>
    <p class="meta">{article.author}{f" &bull; {date_str}" if date_str else ""}</p>
    {content}
</body>
</html>
"""

        chapter = epub.EpubHtml(
            title=article.title,
            file_name=f"{article.slug}.xhtml",
            lang="en",
        )
        chapter.content = chapter_html
        chapter.add_item(css)

        book.add_item(chapter)
        chapters.append(chapter)

    # Define table of contents and spine
    book.toc = [(epub.Section("Articles"), chapters)]
    book.spine = ["nav"] + chapters

    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Write epub file
    output_dir.mkdir(parents=True, exist_ok=True)
    epub_path = output_dir / f"{_slugify(blog_title)}.epub"
    epub.write_epub(str(epub_path), book)

    console.print(f"[green]EPUB export complete: {epub_path}[/green]")
    return epub_path


def _slugify(text: str) -> str:
    """Convert text to a safe filename."""
    import re
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "book"

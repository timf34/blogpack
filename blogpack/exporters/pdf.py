"""Export blog to PDF format."""

from pathlib import Path
from datetime import datetime

from rich.console import Console

from ..platforms.base import Article
from ..cleaner import clean_html, READER_CSS
from ..linker import rewrite_links, get_all_slugs

console = Console()


def export_pdf(
    articles: list[Article],
    output_dir: Path,
    base_url: str,
    image_map: dict[str, Path] | None = None,
    blog_title: str = "Blog Archive",
    blog_author: str = "Unknown",
) -> Path:
    """
    Export articles to PDF format.

    Args:
        articles: List of Article objects
        output_dir: Output directory
        base_url: Original blog URL
        image_map: Dict mapping image URLs to local paths
        blog_title: PDF title
        blog_author: PDF author

    Returns:
        Path to the generated PDF file
    """
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        console.print("[yellow]Warning: weasyprint not available. Skipping PDF export.[/yellow]")
        console.print("[dim]Install with: pip install weasyprint[/dim]")
        return None
    except OSError as e:
        console.print("[yellow]Warning: weasyprint system dependencies missing. Skipping PDF export.[/yellow]")
        console.print(f"[dim]Error: {e}[/dim]")
        console.print("[dim]On Ubuntu/Debian: sudo apt install libpango-1.0-0 libpangocairo-1.0-0[/dim]")
        console.print("[dim]On macOS: brew install pango[/dim]")
        console.print("[dim]On Windows: Install GTK3 from MSYS2[/dim]")
        return None

    console.print(f"[dim]Generating PDF with {len(articles)} articles...[/dim]")

    # Sort articles by date (oldest first)
    sorted_articles = sorted(
        articles,
        key=lambda a: a.date or datetime.min,
    )

    post_slugs = get_all_slugs(articles)

    # Build combined HTML document
    articles_html = []

    # Title page
    articles_html.append(f"""
<div class="title-page">
    <h1>{blog_title}</h1>
    <p class="author">by {blog_author}</p>
    <p class="count">{len(articles)} articles</p>
    <p class="date">Generated {datetime.now().strftime("%B %d, %Y")}</p>
</div>
""")

    # Table of contents
    toc_items = []
    for article in sorted_articles:
        date_str = article.date.strftime("%Y-%m-%d") if article.date else ""
        toc_items.append(f'<li><a href="#{article.slug}">{article.title}</a> <span class="date">{date_str}</span></li>')

    articles_html.append(f"""
<div class="toc">
    <h2>Table of Contents</h2>
    <ol>
        {"".join(toc_items)}
    </ol>
</div>
""")

    # Each article
    for article in sorted_articles:
        date_str = article.date.strftime("%B %d, %Y") if article.date else ""

        content = clean_html(article.content_html)
        content = rewrite_links(content, base_url, post_slugs, image_map)

        # For PDF, convert relative image paths to absolute file:// URLs
        if image_map:
            images_dir = output_dir / "html" / "images"
            for url, local_path in image_map.items():
                abs_path = (images_dir / local_path.name).absolute()
                content = content.replace(
                    f'src="images/{local_path.name}"',
                    f'src="file:///{abs_path}"'
                )

        articles_html.append(f"""
<article id="{article.slug}">
    <h1>{article.title}</h1>
    <p class="meta">{article.author}{f" &bull; {date_str}" if date_str else ""}</p>
    {content}
</article>
""")

    # PDF-specific CSS
    pdf_css = READER_CSS + """
@page {
    size: A4;
    margin: 2cm;
}
.title-page {
    text-align: center;
    page-break-after: always;
    padding-top: 40%;
}
.title-page h1 {
    font-size: 2.5rem;
    margin-bottom: 1rem;
}
.title-page .author {
    font-size: 1.2rem;
    color: #666;
}
.title-page .count, .title-page .date {
    color: #999;
    font-size: 0.9rem;
}
.toc {
    page-break-after: always;
}
.toc ol {
    list-style-position: inside;
}
.toc li {
    padding: 0.3rem 0;
}
.toc .date {
    color: #999;
    font-size: 0.8rem;
}
article {
    page-break-before: always;
}
article:first-of-type {
    page-break-before: auto;
}
"""

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{blog_title}</title>
</head>
<body>
{"".join(articles_html)}
</body>
</html>
"""

    # Generate PDF
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{_slugify(blog_title)}.pdf"

    try:
        html = HTML(string=full_html)
        css = CSS(string=pdf_css)
        html.write_pdf(str(pdf_path), stylesheets=[css])
        console.print(f"[green]PDF export complete: {pdf_path}[/green]")
        return pdf_path
    except OSError as e:
        console.print("[red]PDF export failed: Missing system libraries.[/red]")
        console.print(f"[dim]Error: {e}[/dim]")
        console.print("[dim]On Ubuntu/Debian: sudo apt install libpango-1.0-0 libpangocairo-1.0-0[/dim]")
        console.print("[dim]On macOS: brew install pango[/dim]")
        console.print("[dim]On Windows: Install GTK3 from MSYS2[/dim]")
        return None
    except Exception as e:
        console.print(f"[red]PDF export failed: {e}[/red]")
        return None


def _slugify(text: str) -> str:
    """Convert text to a safe filename."""
    import re
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "book"

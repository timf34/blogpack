"""Export blog to HTML folder."""

from pathlib import Path

from rich.console import Console

from ..platforms.base import Article
from ..cleaner import wrap_article_html, clean_html, READER_CSS
from ..linker import rewrite_links, get_all_slugs

console = Console()


def export_html(
    articles: list[Article],
    output_dir: Path,
    base_url: str,
    image_map: dict[str, Path] | None = None,
    blog_title: str = "Blog Archive",
) -> Path:
    """
    Export articles to a folder of HTML files.

    Args:
        articles: List of Article objects
        output_dir: Base output directory
        base_url: Original blog URL
        image_map: Dict mapping image URLs to local paths
        blog_title: Title for the index page

    Returns:
        Path to the HTML output directory
    """
    html_dir = output_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    # Sort articles by date (newest first)
    sorted_articles = sorted(
        articles,
        key=lambda a: a.date or "",
        reverse=True,
    )

    post_slugs = get_all_slugs(articles)
    console.print(f"[dim]Exporting {len(articles)} articles to HTML...[/dim]")

    # Export each article
    for article in sorted_articles:
        date_str = article.date.strftime("%B %d, %Y") if article.date else ""

        # Clean and rewrite links in content
        content = clean_html(article.content_html)
        content = rewrite_links(content, base_url, post_slugs, image_map)

        # Wrap in full HTML document
        html = wrap_article_html(
            title=article.title,
            author=article.author,
            date_str=date_str,
            content_html=content,
        )

        # Save to file
        filepath = html_dir / f"{article.slug}.html"
        filepath.write_text(html, encoding="utf-8")

    # Generate index page
    index_html = _generate_index(sorted_articles, blog_title)
    (html_dir / "index.html").write_text(index_html, encoding="utf-8")

    console.print(f"[green]HTML export complete: {html_dir}[/green]")
    return html_dir


def _generate_index(articles: list[Article], blog_title: str) -> str:
    """Generate the index.html table of contents."""
    toc_items = []
    for article in articles:
        date_str = article.date.strftime("%Y-%m-%d") if article.date else ""
        date_span = f' <span class="date">({date_str})</span>' if date_str else ""
        toc_items.append(
            f'<li><a href="{article.slug}.html">{article.title}</a>{date_span}</li>'
        )

    toc_html = "\n".join(toc_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{blog_title}</title>
    <style>
{READER_CSS}
ul {{
    list-style: none;
    padding: 0;
}}
li {{
    padding: 0.5rem 0;
    border-bottom: 1px solid #eee;
}}
li a {{
    text-decoration: none;
}}
li a:hover {{
    text-decoration: underline;
}}
.date {{
    color: #666;
    font-size: 0.85rem;
}}
    </style>
</head>
<body>
    <h1>{blog_title}</h1>
    <p>{len(articles)} articles</p>
    <ul>
{toc_html}
    </ul>
</body>
</html>
"""

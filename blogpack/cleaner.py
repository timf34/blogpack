"""Clean and normalize article HTML content."""

import re
from bs4 import BeautifulSoup

# Minimal CSS for pleasant reading
READER_CSS = """
body {
    max-width: 700px;
    margin: 2rem auto;
    padding: 0 1rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 18px;
    line-height: 1.6;
    color: #333;
    background: #fff;
}
h1 {
    font-size: 2rem;
    margin-bottom: 0.5rem;
    line-height: 1.2;
}
h2 {
    font-size: 1.5rem;
    margin-top: 2rem;
}
h3 {
    font-size: 1.25rem;
    margin-top: 1.5rem;
}
.meta {
    color: #666;
    font-size: 0.9rem;
    margin-bottom: 2rem;
}
img {
    max-width: 100%;
    height: auto;
    margin: 1rem 0;
}
blockquote {
    border-left: 4px solid #ddd;
    margin: 1rem 0;
    padding-left: 1rem;
    color: #555;
}
pre, code {
    background: #f5f5f5;
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
    font-size: 0.9em;
}
pre {
    padding: 1rem;
    overflow-x: auto;
}
a {
    color: #0066cc;
}
a:hover {
    text-decoration: underline;
}
figure {
    margin: 1.5rem 0;
}
figcaption {
    font-size: 0.9rem;
    color: #666;
    text-align: center;
    margin-top: 0.5rem;
}
hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 2rem 0;
}
"""


def clean_html(content_html: str) -> str:
    """
    Clean and normalize HTML content.

    Removes scripts, styles, unwanted attributes, and wrapper tags.
    """
    # Remove Ghost CMS kg-card comments (they get mangled by parser)
    content_html = re.sub(r'<!--kg-card-(?:begin|end): \w+-->', '', content_html)
    # Also remove if they've already been mangled into text
    content_html = re.sub(r'kg-card-(?:begin|end): \w+', '', content_html)

    soup = BeautifulSoup(content_html, "lxml")

    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "iframe", "noscript"]):
        tag.decompose()

    # Remove unwanted attributes (tracking, styles that might break)
    attrs_to_remove = ["onclick", "onload", "style", "class", "id"]
    for tag in soup.find_all(True):
        for attr in attrs_to_remove:
            if attr in tag.attrs:
                del tag.attrs[attr]

    # Extract just the body content, not the html/body wrapper
    body = soup.find("body")
    if body:
        # Get inner HTML of body
        return "".join(str(child) for child in body.children)

    return str(soup)


def wrap_article_html(
    title: str,
    author: str,
    date_str: str,
    content_html: str,
    include_css: bool = True,
) -> str:
    """
    Wrap article content in a complete HTML document.

    Args:
        title: Article title
        author: Article author
        date_str: Formatted date string
        content_html: The main article content
        include_css: Whether to include reader CSS

    Returns:
        Complete HTML document string
    """
    css = f"<style>{READER_CSS}</style>" if include_css else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {css}
</head>
<body>
    <article>
        <h1>{title}</h1>
        <div class="meta">
            <span class="author">{author}</span>
            {f' &bull; <span class="date">{date_str}</span>' if date_str else ''}
        </div>
        {content_html}
    </article>
</body>
</html>
"""

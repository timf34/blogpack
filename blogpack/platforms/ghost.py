"""Ghost blog platform support."""

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .base import BlogPlatform, Article, PostInfo


class GhostPlatform(BlogPlatform):
    """Support for Ghost blogs."""

    name = "ghost"

    def detect(self, html: str) -> bool:
        """Detect Ghost blogs by footer text or meta tags."""
        html_lower = html.lower()
        indicators = [
            "powered by ghost",
            'content="ghost"',
            "ghost.org",
            'generator" content="ghost',
        ]
        return any(indicator in html_lower for indicator in indicators)

    async def get_post_urls(self, base_url: str, client) -> list[PostInfo]:
        """Fetch post URLs from Ghost's sitemap-posts.xml."""
        sitemap_url = urljoin(base_url, "/sitemap-posts.xml")
        response = await client.get(sitemap_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml-xml")
        posts = []

        for url_elem in soup.find_all("url"):
            loc = url_elem.find("loc")
            lastmod = url_elem.find("lastmod")

            if loc:
                url = loc.text.strip()
                slug = self._url_to_slug(url, base_url)

                modified = None
                if lastmod:
                    try:
                        modified = datetime.fromisoformat(lastmod.text.strip().replace("Z", "+00:00"))
                    except ValueError:
                        pass

                posts.append(PostInfo(url=url, slug=slug, last_modified=modified))

        return posts

    def _url_to_slug(self, url: str, base_url: str) -> str:
        """Extract slug from URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        return path if path else "index"

    def extract_article(self, html: str, url: str) -> Article:
        """Extract clean article content from Ghost post HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Extract title
        title = self._extract_title(soup)

        # Extract author
        author = self._extract_author(soup)

        # Extract date
        date = self._extract_date(soup)

        # Extract main content
        content_html = self._extract_content(soup)

        # Extract image URLs from content
        image_urls = self._extract_images(soup, url)

        slug = self._url_to_slug(url, "")

        return Article(
            url=url,
            slug=slug,
            title=title,
            author=author,
            date=date,
            content_html=content_html,
            image_urls=image_urls,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title."""
        # Try various selectors
        selectors = [
            "h1.post-full-title",
            "h1.article-title",
            "h1.post-title",
            "article h1",
            "h1",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Fallback to og:title or title tag
        og_title = soup.find("meta", property="og:title")
        if og_title:
            return og_title.get("content", "Untitled")

        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True).split("|")[0].strip()

        return "Untitled"

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract article author."""
        # Try meta tag first
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            return author_meta.get("content")

        # Try twitter:creator
        twitter_author = soup.find("meta", {"name": "twitter:creator"})
        if twitter_author and twitter_author.get("content"):
            return twitter_author.get("content").lstrip("@")

        # Try link with title attribute (common in Ghost themes)
        author_link = soup.select_one('a[title][href*="/about"]')
        if author_link and author_link.get("title"):
            return author_link.get("title")

        # Try schema.org author
        author_elem = soup.select_one('[rel="author"]')
        if author_elem:
            return author_elem.get_text(strip=True)

        # Try byline class
        byline = soup.select_one(".byline-name, .author-name, .post-full-byline-content")
        if byline:
            return byline.get_text(strip=True)

        return "Unknown"

    def _extract_date(self, soup: BeautifulSoup) -> datetime | None:
        """Extract publication date."""
        # Try time element
        time_elem = soup.find("time", datetime=True)
        if time_elem:
            try:
                return datetime.fromisoformat(time_elem["datetime"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Try meta tag
        date_meta = soup.find("meta", property="article:published_time")
        if date_meta:
            try:
                return datetime.fromisoformat(date_meta["content"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return None

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main article content HTML."""
        # Try various content selectors - prefer more specific ones first
        selectors = [
            "div.single-content",  # Cold Takes theme
            "div.gh-content",
            "section.post-full-content .post-content",
            "section.post-full-content",
            "div.post-content",
            "article .post-content",
            "article .content",
        ]

        content_elem = None
        for selector in selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                break

        # Fallback: try to find main content area but exclude header/byline
        if not content_elem:
            article = soup.select_one("article")
            if article:
                # Clone and remove header/byline from the clone
                content_elem = article
            else:
                return "<p>Content could not be extracted.</p>"

        # Remove unwanted elements
        for unwanted in content_elem.select(
            "script, style, nav, header, footer, .subscribe-form, "
            ".post-full-byline, .post-full-meta, .kg-signup-card, .related-posts, "
            ".comments, .share-buttons, .social-links, .post-full-header"
        ):
            unwanted.decompose()

        # Get inner HTML (children only, not the wrapper element)
        inner_html = "".join(str(child) for child in content_elem.children)
        return inner_html if inner_html.strip() else str(content_elem)

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract all image URLs from the article."""
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                # Skip data URLs and blob URLs
                if src.startswith(("data:", "blob:")):
                    continue
                # Make absolute URL
                absolute_url = urljoin(base_url, src)
                images.append(absolute_url)
        return images

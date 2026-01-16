"""Substack blog platform support."""

import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .base import BlogPlatform, Article, PostInfo


class SubstackPlatform(BlogPlatform):
    """Support for Substack blogs."""

    name = "substack"

    # URLs containing these keywords are not posts
    FILTER_KEYWORDS = ["about", "archive", "podcast", "subscribe", "recommendations"]

    def detect(self, html: str) -> bool:
        """Detect Substack blogs by checking for Substack-specific indicators."""
        html_lower = html.lower()
        indicators = [
            "substack.com",
            "substackcdn.com",
            'content="substack"',
            "substack-post",
            "substack.com/app",
        ]
        return any(indicator in html_lower for indicator in indicators)

    async def get_post_urls(self, base_url: str, client) -> list[PostInfo]:
        """Fetch post URLs from Substack's sitemap.xml, fallback to feed.xml."""
        posts = await self._fetch_from_sitemap(base_url, client)
        if not posts:
            posts = await self._fetch_from_feed(base_url, client)
        return self._filter_urls(posts)

    async def _fetch_from_sitemap(self, base_url: str, client) -> list[PostInfo]:
        """Fetch URLs from sitemap.xml."""
        sitemap_url = urljoin(base_url, "/sitemap.xml")
        try:
            response = await client.get(sitemap_url)
            if not response.is_success:
                return []

            root = ET.fromstring(response.content)
            posts = []

            # Handle both regular sitemaps and sitemap indexes
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Check if this is a sitemap index
            sitemap_refs = root.findall(".//sm:sitemap/sm:loc", ns)
            if sitemap_refs:
                # It's a sitemap index - fetch the post sitemap
                for ref in sitemap_refs:
                    if "posts" in ref.text.lower():
                        sub_response = await client.get(ref.text)
                        if sub_response.is_success:
                            sub_root = ET.fromstring(sub_response.content)
                            posts.extend(self._parse_sitemap_urls(sub_root, ns, base_url))
            else:
                # Regular sitemap
                posts = self._parse_sitemap_urls(root, ns, base_url)

            return posts
        except Exception:
            return []

    def _parse_sitemap_urls(self, root, ns: dict, base_url: str) -> list[PostInfo]:
        """Parse URLs from a sitemap XML element."""
        posts = []
        for url_elem in root.findall(".//sm:url", ns):
            loc = url_elem.find("sm:loc", ns)
            lastmod = url_elem.find("sm:lastmod", ns)

            if loc is not None and loc.text:
                url = loc.text.strip()
                slug = self._url_to_slug(url)

                modified = None
                if lastmod is not None and lastmod.text:
                    try:
                        modified = datetime.fromisoformat(
                            lastmod.text.strip().replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                posts.append(PostInfo(url=url, slug=slug, last_modified=modified))

        return posts

    async def _fetch_from_feed(self, base_url: str, client) -> list[PostInfo]:
        """Fetch URLs from feed.xml (fallback, only ~22 recent posts)."""
        feed_url = urljoin(base_url, "/feed")
        try:
            response = await client.get(feed_url)
            if not response.is_success:
                return []

            root = ET.fromstring(response.content)
            posts = []

            for item in root.findall(".//item"):
                link = item.find("link")
                if link is not None and link.text:
                    url = link.text.strip()
                    slug = self._url_to_slug(url)
                    posts.append(PostInfo(url=url, slug=slug))

            return posts
        except Exception:
            return []

    def _filter_urls(self, posts: list[PostInfo]) -> list[PostInfo]:
        """Filter out non-post URLs."""
        return [
            post for post in posts
            if all(kw not in post.url.lower() for kw in self.FILTER_KEYWORDS)
            and "/p/" in post.url  # Substack posts have /p/ in the URL
        ]

    def _url_to_slug(self, url: str) -> str:
        """Extract slug from URL."""
        parsed = urlparse(url)
        # Substack URLs are like: https://blog.substack.com/p/post-title
        path = parsed.path.strip("/")
        if path.startswith("p/"):
            path = path[2:]  # Remove "p/" prefix
        return path if path else "index"

    def extract_article(self, html: str, url: str) -> Article | None:
        """Extract article content from Substack post HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Check for paywall - skip premium posts
        if self._is_paywalled(soup):
            return None

        # Extract metadata from JSON-LD first (most reliable)
        metadata = self._extract_json_ld(soup)

        # Extract title
        title = metadata.get("title") or self._extract_title(soup)

        # Extract author
        author = metadata.get("author") or self._extract_author(soup)

        # Extract date
        date = metadata.get("date") or self._extract_date(soup)

        # Extract subtitle
        subtitle = self._extract_subtitle(soup)

        # Extract main content
        content_html = self._extract_content(soup, subtitle)

        # Extract image URLs
        image_urls = self._extract_images(soup, url)

        slug = self._url_to_slug(url)

        return Article(
            url=url,
            slug=slug,
            title=title,
            author=author,
            date=date,
            content_html=content_html,
            image_urls=image_urls,
        )

    def _is_paywalled(self, soup: BeautifulSoup) -> bool:
        """Check if the post is behind a paywall."""
        # Check for paywall title
        paywall_title = soup.find("h2", class_="paywall-title")
        if paywall_title:
            return True

        # Check for paywall div
        paywall_div = soup.find("div", class_="paywall")
        if paywall_div:
            return True

        # Check for "Subscribe to continue" type messages
        paywall_indicators = [
            "subscribe to continue",
            "this post is for paid subscribers",
            "upgrade to paid",
            "become a paid subscriber",
        ]
        text_content = soup.get_text().lower()
        # Only check in the content area, not the whole page
        content_area = soup.find("div", class_="available-content")
        if content_area:
            content_text = content_area.get_text().lower()
            if any(indicator in content_text for indicator in paywall_indicators):
                return True

        return False

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict:
        """Extract metadata from JSON-LD script tag."""
        result = {"title": None, "author": None, "date": None}

        script_tag = soup.find("script", {"type": "application/ld+json"})
        if not script_tag or not script_tag.string:
            return result

        try:
            data = json.loads(script_tag.string)

            # Handle array of JSON-LD objects
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") in ["Article", "NewsArticle", "BlogPosting"]:
                        data = item
                        break
                else:
                    return result

            # Extract title
            result["title"] = data.get("headline") or data.get("name")

            # Extract author
            author_data = data.get("author")
            if isinstance(author_data, dict):
                result["author"] = author_data.get("name")
            elif isinstance(author_data, list) and author_data:
                result["author"] = author_data[0].get("name") if isinstance(author_data[0], dict) else str(author_data[0])
            elif isinstance(author_data, str):
                result["author"] = author_data

            # Extract date
            date_str = data.get("datePublished") or data.get("dateCreated")
            if date_str:
                try:
                    result["date"] = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return result

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title from HTML."""
        selectors = [
            "h1.post-title",
            "h2.post-title",
            "h1",
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Fallback to og:title
        og_title = soup.find("meta", property="og:title")
        if og_title:
            return og_title.get("content", "Untitled")

        return "Untitled"

    def _extract_subtitle(self, soup: BeautifulSoup) -> str:
        """Extract article subtitle."""
        subtitle_elem = soup.select_one("h3.subtitle")
        if subtitle_elem:
            return subtitle_elem.get_text(strip=True)
        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract article author."""
        # Try meta tag
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            return author_meta.get("content")

        # Try author link
        author_link = soup.select_one("a.frontend-pencraft-Text-module__decoration-hover-underline--BEYAn")
        if author_link:
            return author_link.get_text(strip=True)

        return "Unknown"

    def _extract_date(self, soup: BeautifulSoup) -> datetime | None:
        """Extract publication date."""
        # Try time element
        time_elem = soup.find("time", datetime=True)
        if time_elem:
            try:
                return datetime.fromisoformat(
                    time_elem["datetime"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        return None

    def _extract_content(self, soup: BeautifulSoup, subtitle: str) -> str:
        """Extract main article content HTML."""
        # Substack content is in div.available-content
        content_elem = soup.select_one("div.available-content")

        if not content_elem:
            # Fallback selectors
            content_elem = soup.select_one("div.body")
            if not content_elem:
                content_elem = soup.select_one("article")

        if not content_elem:
            return "<p>Content could not be extracted.</p>"

        # Remove unwanted elements
        for unwanted in content_elem.select(
            "script, style, .subscription-widget, .subscribe-widget, "
            ".post-ufi, .post-footer, .comments-section, .share-dialog"
        ):
            unwanted.decompose()

        # Prepend subtitle if present
        content_html = ""
        if subtitle:
            content_html = f"<p><em>{subtitle}</em></p>\n"

        content_html += str(content_elem)
        return content_html

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract all image URLs from the article."""
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                # Skip data URLs, tracking pixels, etc.
                if src.startswith(("data:", "blob:")):
                    continue
                if "tracking" in src.lower() or "pixel" in src.lower():
                    continue
                # Make absolute URL
                absolute_url = urljoin(base_url, src)
                images.append(absolute_url)
        return images

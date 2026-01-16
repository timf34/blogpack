"""WordPress blog platform support."""

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .base import BlogPlatform, Article, PostInfo


class WordPressPlatform(BlogPlatform):
    """Support for WordPress blogs."""

    name = "wordpress"

    # URLs containing these keywords are not posts
    FILTER_KEYWORDS = ["wp-admin", "wp-login", "wp-content", "attachment", "page", "author", "category", "tag"]

    # Content selectors in order of preference
    CONTENT_SELECTORS = [
        "article .entry-content",
        "div.entry-content",
        "div.post-content",
        "article .post-body",
        "div.single-content",
        ".content-area article",
        "article",
    ]

    TITLE_SELECTORS = [
        "h1.entry-title",
        "h1.post-title",
        "article h1",
        ".post-title",
        "h1",
    ]

    def detect(self, html: str) -> bool:
        """Detect WordPress blogs by checking for WordPress-specific indicators."""
        html_lower = html.lower()
        indicators = [
            "/wp-content/",
            "/wp-includes/",
            "wp-json",
            'generator" content="wordpress',
            "wordpress.org",
            "wp-block-",
            "wp-embed",
        ]
        return any(indicator in html_lower for indicator in indicators)

    async def get_post_urls(self, base_url: str, client) -> list[PostInfo]:
        """Fetch post URLs from WordPress REST API, fallback to sitemap/feed."""
        # Try REST API first (most reliable)
        posts = await self._fetch_from_rest_api(base_url, client)
        if posts:
            return posts

        # Fallback to sitemap
        posts = await self._fetch_from_sitemap(base_url, client)
        if posts:
            return self._filter_urls(posts)

        # Final fallback to RSS feed
        posts = await self._fetch_from_feed(base_url, client)
        return self._filter_urls(posts)

    async def _fetch_from_rest_api(self, base_url: str, client) -> list[PostInfo]:
        """Fetch all posts via WordPress REST API with pagination."""
        posts = []
        page = 1
        per_page = 100  # Max allowed by WordPress

        while True:
            api_url = urljoin(base_url, f"wp-json/wp/v2/posts?per_page={per_page}&page={page}&_fields=link,slug,modified")
            try:
                response = await client.get(api_url)

                # 400 = invalid page (past end), 404 = API not available
                if response.status_code in (400, 404):
                    break
                if not response.is_success:
                    return []  # API not available, use fallback

                data = response.json()
                if not data:
                    break

                for post in data:
                    modified = None
                    if post.get("modified"):
                        try:
                            modified = datetime.fromisoformat(
                                post["modified"].replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                    posts.append(PostInfo(
                        url=post["link"],
                        slug=post["slug"],
                        last_modified=modified,
                    ))

                # Check for more pages via header
                total_pages = int(response.headers.get("X-WP-TotalPages", 1))
                if page >= total_pages:
                    break
                page += 1

            except Exception:
                # API failed, return what we have or empty
                return posts if posts else []

        return posts

    async def _fetch_from_sitemap(self, base_url: str, client) -> list[PostInfo]:
        """Fetch URLs from sitemap.xml."""
        sitemap_urls = [
            urljoin(base_url, "/sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xml"),
            urljoin(base_url, "/post-sitemap.xml"),
        ]

        for sitemap_url in sitemap_urls:
            try:
                response = await client.get(sitemap_url)
                if not response.is_success:
                    continue

                root = ET.fromstring(response.content)
                posts = []

                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                # Check if this is a sitemap index
                sitemap_refs = root.findall(".//sm:sitemap/sm:loc", ns)
                if sitemap_refs:
                    # It's a sitemap index - look for post sitemap
                    for ref in sitemap_refs:
                        if ref.text and "post" in ref.text.lower():
                            sub_response = await client.get(ref.text)
                            if sub_response.is_success:
                                sub_root = ET.fromstring(sub_response.content)
                                posts.extend(self._parse_sitemap_urls(sub_root, ns))
                    if posts:
                        return posts

                # Regular sitemap
                posts = self._parse_sitemap_urls(root, ns)
                if posts:
                    return posts

            except Exception:
                continue

        return []

    def _parse_sitemap_urls(self, root, ns: dict) -> list[PostInfo]:
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
        """Fetch URLs from RSS feed (fallback, limited posts)."""
        feed_urls = [
            urljoin(base_url, "/feed/"),
            urljoin(base_url, "/feed"),
            urljoin(base_url, "/rss"),
        ]

        for feed_url in feed_urls:
            try:
                response = await client.get(feed_url)
                if not response.is_success:
                    continue

                root = ET.fromstring(response.content)
                posts = []

                for item in root.findall(".//item"):
                    link = item.find("link")
                    if link is not None and link.text:
                        url = link.text.strip()
                        slug = self._url_to_slug(url)
                        posts.append(PostInfo(url=url, slug=slug))

                if posts:
                    return posts

            except Exception:
                continue

        return []

    def _filter_urls(self, posts: list[PostInfo]) -> list[PostInfo]:
        """Filter out non-post URLs."""
        filtered = []
        for post in posts:
            url_lower = post.url.lower()
            # Skip if URL contains filter keywords
            if any(kw in url_lower for kw in self.FILTER_KEYWORDS):
                continue
            # Skip if it's just the homepage
            parsed = urlparse(post.url)
            if not parsed.path or parsed.path == "/":
                continue
            filtered.append(post)
        return filtered

    def _url_to_slug(self, url: str) -> str:
        """Extract slug from URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        # WordPress URLs can be /year/month/day/slug or just /slug
        # Take the last path segment as the slug
        parts = path.split("/")
        slug = parts[-1] if parts else "index"
        # Remove .html extension if present (Wait But Why uses .html URLs)
        if slug.endswith(".html"):
            slug = slug[:-5]
        return slug

    def extract_article(self, html: str, url: str) -> Article | None:
        """Extract article content from WordPress post HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Check for paywall
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

        # Extract main content
        content_html = self._extract_content(soup)

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
        # Check for common membership plugin classes
        paywall_classes = [
            "members-only",
            "protected-content",
            "paywall",
            "subscriber-only",
            "premium-content",
            "restricted-content",
        ]
        for cls in paywall_classes:
            if soup.find(class_=re.compile(cls, re.IGNORECASE)):
                return True

        # Check for login prompts in content area
        for selector in self.CONTENT_SELECTORS[:3]:  # Check main content selectors
            content = soup.select_one(selector)
            if content:
                text = content.get_text().lower()
                paywall_indicators = [
                    "log in to view",
                    "members only",
                    "subscribe to read",
                    "premium members",
                    "login to continue",
                ]
                if any(indicator in text for indicator in paywall_indicators):
                    return True
                break

        return False

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict:
        """Extract metadata from JSON-LD script tag."""
        import json

        result = {"title": None, "author": None, "date": None}

        for script_tag in soup.find_all("script", {"type": "application/ld+json"}):
            if not script_tag.string:
                continue

            try:
                data = json.loads(script_tag.string)

                # Handle array of JSON-LD objects
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") in ["Article", "NewsArticle", "BlogPosting", "WebPage"]:
                            data = item
                            break
                    else:
                        continue

                # Skip if not an article type
                if data.get("@type") not in ["Article", "NewsArticle", "BlogPosting", "WebPage", None]:
                    continue

                # Extract title
                if not result["title"]:
                    result["title"] = data.get("headline") or data.get("name")

                # Extract author
                if not result["author"]:
                    author_data = data.get("author")
                    if isinstance(author_data, dict):
                        result["author"] = author_data.get("name")
                    elif isinstance(author_data, list) and author_data:
                        result["author"] = author_data[0].get("name") if isinstance(author_data[0], dict) else str(author_data[0])
                    elif isinstance(author_data, str):
                        result["author"] = author_data

                # Extract date
                if not result["date"]:
                    date_str = data.get("datePublished") or data.get("dateCreated")
                    if date_str:
                        try:
                            result["date"] = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return result

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title from HTML."""
        for selector in self.TITLE_SELECTORS:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Fallback to og:title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title.get("content")

        # Fallback to page title
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remove site name (usually after | or -)
            for sep in [" | ", " - ", " :: "]:
                if sep in title:
                    title = title.split(sep)[0].strip()
                    break
            return title

        return "Untitled"

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract article author."""
        # Try meta tag
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            return author_meta.get("content")

        # Try common author selectors
        author_selectors = [
            ".author-name",
            ".entry-author-name",
            ".post-author-name",
            'a[rel="author"]',
            ".byline a",
            ".author a",
        ]
        for selector in author_selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        return "Unknown"

    def _extract_date(self, soup: BeautifulSoup) -> datetime | None:
        """Extract publication date."""
        # Try time element with datetime attribute
        time_elem = soup.find("time", datetime=True)
        if time_elem:
            try:
                return datetime.fromisoformat(
                    time_elem["datetime"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Try meta tag
        date_meta = soup.find("meta", property="article:published_time")
        if date_meta and date_meta.get("content"):
            try:
                return datetime.fromisoformat(
                    date_meta["content"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        return None

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main article content HTML."""
        content_elem = None

        for selector in self.CONTENT_SELECTORS:
            content_elem = soup.select_one(selector)
            if content_elem:
                break

        if not content_elem:
            return "<p>Content could not be extracted.</p>"

        # Remove unwanted elements
        unwanted_selectors = [
            "script", "style", "nav", "header", "footer",
            ".sidebar", ".widget", ".ad", ".advertisement",
            ".share-buttons", ".social-share", ".related-posts",
            ".comments", ".comment-form", ".author-bio",
            ".post-navigation", ".pagination", ".breadcrumbs",
            "form", "iframe[src*='ad']",
        ]
        for unwanted in content_elem.select(", ".join(unwanted_selectors)):
            unwanted.decompose()

        return str(content_elem)

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract all image URLs from the article."""
        images = []
        for img in soup.find_all("img"):
            # Try multiple src attributes
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                # Skip data URLs and tracking pixels
                if src.startswith(("data:", "blob:")):
                    continue
                if any(x in src.lower() for x in ["tracking", "pixel", "1x1", "spacer"]):
                    continue
                # Make absolute URL
                absolute_url = urljoin(base_url, src)
                images.append(absolute_url)

            # Also check srcset for high-res images
            srcset = img.get("srcset")
            if srcset:
                # Take the largest image from srcset
                parts = srcset.split(",")
                for part in parts:
                    part = part.strip().split()[0]
                    if part and not part.startswith("data:"):
                        absolute_url = urljoin(base_url, part)
                        if absolute_url not in images:
                            images.append(absolute_url)

        return images

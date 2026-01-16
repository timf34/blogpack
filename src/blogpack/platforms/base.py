"""Base class for blog platform support."""

from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod


@dataclass
class Article:
    """Represents a parsed blog article."""
    url: str
    slug: str
    title: str
    author: str
    date: datetime | None
    content_html: str
    image_urls: list[str] = field(default_factory=list)


@dataclass
class PostInfo:
    """Basic info about a post from sitemap/index."""
    url: str
    slug: str
    last_modified: datetime | None = None


class BlogPlatform(ABC):
    """Base class for blog platform support."""

    name: str = "unknown"

    @abstractmethod
    def detect(self, html: str) -> bool:
        """Return True if this platform matches the blog."""
        raise NotImplementedError

    @abstractmethod
    async def get_post_urls(self, base_url: str, client) -> list[PostInfo]:
        """Fetch all post URLs from sitemap/RSS/archive."""
        raise NotImplementedError

    @abstractmethod
    def extract_article(self, html: str, url: str) -> Article:
        """Extract clean article content from post HTML."""
        raise NotImplementedError

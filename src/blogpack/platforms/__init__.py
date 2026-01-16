"""Blog platform detection and parsing."""

from .base import BlogPlatform, Article
from .ghost import GhostPlatform

PLATFORMS = [GhostPlatform()]


def detect_platform(html: str) -> BlogPlatform | None:
    """Auto-detect blog platform from homepage HTML."""
    for platform in PLATFORMS:
        if platform.detect(html):
            return platform
    return None


__all__ = ["BlogPlatform", "Article", "GhostPlatform", "detect_platform", "PLATFORMS"]

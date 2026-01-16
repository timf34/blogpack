"""Blog platform detection and parsing."""

from .base import BlogPlatform, Article
from .ghost import GhostPlatform
from .substack import SubstackPlatform
from .wordpress import WordPressPlatform

PLATFORMS = [GhostPlatform(), SubstackPlatform(), WordPressPlatform()]


def detect_platform(html: str) -> BlogPlatform | None:
    """Auto-detect blog platform from homepage HTML."""
    for platform in PLATFORMS:
        if platform.detect(html):
            return platform
    return None


__all__ = ["BlogPlatform", "Article", "GhostPlatform", "SubstackPlatform", "WordPressPlatform", "detect_platform", "PLATFORMS"]

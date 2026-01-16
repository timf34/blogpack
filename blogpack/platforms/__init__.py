"""Blog platform detection and parsing."""

from .base import BlogPlatform, Article
from .ghost import GhostPlatform
from .substack import SubstackPlatform

PLATFORMS = [GhostPlatform(), SubstackPlatform()]


def detect_platform(html: str) -> BlogPlatform | None:
    """Auto-detect blog platform from homepage HTML."""
    for platform in PLATFORMS:
        if platform.detect(html):
            return platform
    return None


__all__ = ["BlogPlatform", "Article", "GhostPlatform", "SubstackPlatform", "detect_platform", "PLATFORMS"]

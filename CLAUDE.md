# Blogpack Codebase Documentation

This document explains the blogpack codebase for developers and LLMs.

## Overview

Blogpack downloads entire blogs and converts them to offline-readable formats (PDF, EPUB, HTML). It has two interfaces:

1. **CLI** (`blogpack/cli.py`) - Command-line tool for local use
2. **Web App** (`blogpack-web/`) - Browser-based interface hosted on a server

## Project Structure

```
blogpack/
├── blogpack/                  # Core library (CLI + shared logic)
│   ├── cli.py                 # CLI entry point (Typer)
│   ├── crawler.py             # Discovers all posts on a blog
│   ├── downloader.py          # Downloads posts and images
│   ├── cleaner.py             # Sanitizes HTML, adds reader CSS
│   ├── linker.py              # Rewrites links for offline reading
│   ├── platforms/             # Platform-specific handlers
│   │   ├── base.py            # Abstract base class + data models
│   │   ├── ghost.py           # Ghost blog support
│   │   ├── substack.py        # Substack support
│   │   └── wordpress.py       # WordPress support
│   └── exporters/             # Output format generators
│       ├── html.py            # HTML folder with index
│       ├── epub.py            # EPUB ebook file
│       └── pdf.py             # PDF document
├── blogpack-web/              # Web application
│   ├── app.py                 # FastAPI backend
│   ├── static/index.html      # Frontend (single HTML file)
│   └── requirements.txt       # Web dependencies
├── Dockerfile                 # Container for deployment
├── pyproject.toml             # Package configuration
└── README.md                  # User documentation
```

---

## Core Library (`blogpack/`)

### Data Flow

```
URL Input
    ↓
┌─────────────────────────────────────────┐
│ crawler.py: discover_posts()            │
│ - Fetches homepage                      │
│ - Auto-detects platform (Ghost, etc.)   │
│ - Gets post list from sitemap/RSS       │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ downloader.py: download_posts()         │
│ - Downloads each post HTML              │
│ - Extracts article content via platform │
│ - Downloads all images                  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ exporters/*.py                          │
│ - Cleans HTML (cleaner.py)              │
│ - Rewrites links (linker.py)            │
│ - Generates PDF/EPUB/HTML output        │
└─────────────────────────────────────────┘
```

### Key Modules

#### `crawler.py`

**Purpose:** Discover all blog posts from a URL.

```python
async def discover_posts(base_url: str, platform: BlogPlatform | None = None) -> tuple[BlogPlatform, list[PostInfo]]
```

- If `platform` is None, auto-detects by fetching homepage and checking HTML markers
- Returns the detected platform handler and list of `PostInfo` objects
- Uses `httpx.AsyncClient` for async HTTP requests

#### `downloader.py`

**Purpose:** Download post content and images.

```python
async def download_posts(
    base_url: str,
    posts: list[PostInfo],
    platform: BlogPlatform,
    include_images: bool = True,
    output_dir: Path | None = None,
) -> tuple[list[Article], dict[str, Path]]
```

- Downloads posts concurrently with rate limiting (platform-specific)
- Handles 429 rate limits with exponential backoff
- Downloads images to `output_dir/images/` with content-hash filenames
- Returns `Article` objects and a map of image URL → local path

#### `cleaner.py`

**Purpose:** Sanitize HTML for offline reading.

- `clean_html(content_html)` - Removes scripts, iframes, tracking pixels, ads
- `wrap_article_html(title, author, date_str, content_html)` - Wraps content in a full HTML document with reader-friendly CSS
- `READER_CSS` - Embedded stylesheet for pleasant reading

#### `linker.py`

**Purpose:** Rewrite links for offline navigation.

```python
def rewrite_links(html, base_url, post_slugs, image_map, relative_image_path="images") -> str
```

- Converts internal blog links to local file references (e.g., `cold-takes.com/post-slug` → `post-slug.html`)
- Converts image URLs to local paths (e.g., `https://cdn.com/img.jpg` → `images/abc123.jpg`)

#### `platforms/base.py`

**Purpose:** Abstract base class and data models.

```python
@dataclass
class PostInfo:
    url: str
    slug: str
    last_modified: datetime | None

@dataclass
class Article:
    url: str
    slug: str
    title: str
    author: str
    date: datetime | None
    content_html: str
    image_urls: list[str]

class BlogPlatform(ABC):
    name: str

    @abstractmethod
    def detect(self, html: str) -> bool: ...

    @abstractmethod
    async def get_post_urls(self, base_url: str, client: AsyncClient) -> list[PostInfo]: ...

    @abstractmethod
    def extract_article(self, html: str, url: str) -> Article | None: ...
```

#### `platforms/ghost.py`, `substack.py`, `wordpress.py`

**Purpose:** Platform-specific implementations.

Each platform handler:
- `detect()` - Checks HTML for platform markers (e.g., "powered by ghost", meta tags)
- `get_post_urls()` - Fetches post list (typically from sitemap XML)
- `extract_article()` - Parses article content from HTML using platform-specific selectors

#### `exporters/html.py`

```python
def export_html(articles, output_dir, base_url, image_map, blog_title) -> Path
```

- Creates `output_dir/html/` folder
- One HTML file per article (`post-slug.html`)
- Generates `index.html` with table of contents
- Copies images to `html/images/`

#### `exporters/epub.py`

```python
def export_epub(articles, output_dir, base_url, image_map, blog_title, blog_author) -> Path
```

- Creates single `.epub` file using `ebooklib`
- Each article becomes a chapter
- Images embedded in the EPUB
- Internal links work between chapters

#### `exporters/pdf.py`

```python
def export_pdf(articles, output_dir, base_url, image_map, blog_title, blog_author) -> Path
```

- Creates single `.pdf` file using `weasyprint`
- Includes title page, table of contents, all articles
- Page breaks between articles

---

## CLI (`blogpack/cli.py`)

Entry point for command-line usage. Built with Typer.

```python
@app.command()
def main(
    url: str,                              # Blog URL
    output: Path = Path("./output"),       # Output directory
    format: str = "all",                   # all, epub, html, pdf
    images: bool = True,                   # Download images
    platform: str = None,                  # Force platform detection
)
```

**Usage:**
```bash
blogpack https://www.cold-takes.com/ -o ./cold-takes -f epub
```

---

## Web App (`blogpack-web/`)

### Architecture

```
Browser                         Server (FastAPI)
   │                                  │
   │  POST /process {url, formats}    │
   │ ─────────────────────────────────>
   │                                  │ Creates job, starts background task
   │  {"job_id": "abc123"}            │
   │ <─────────────────────────────────
   │                                  │
   │  GET /status/abc123 (polling)    │
   │ ─────────────────────────────────>
   │  {"status": "processing"}        │
   │ <─────────────────────────────────
   │           ...                    │
   │  {"status": "complete"}          │
   │ <─────────────────────────────────
   │                                  │
   │  GET /download/abc123            │
   │ ─────────────────────────────────>
   │  [ZIP file stream]               │
   │ <─────────────────────────────────
   │                                  │ Deletes temp files after download
```

### Backend (`app.py`)

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves frontend HTML |
| `/process` | POST | Starts a new job, returns `{job_id}` |
| `/status/{job_id}` | GET | Returns job status and progress |
| `/download/{job_id}` | GET | Streams ZIP file, then deletes temp files |

**Key Features:**

- **Concurrency limit:** `MAX_CONCURRENT_JOBS = 3` - Returns 503 if too busy
- **Post limit:** `MAX_POSTS = 100` - Hard cap on posts per request
- **In-memory job tracking:** Simple dict, no Redis needed
- **Auto-cleanup:** Temp files deleted after download or after 1 hour

**Background Processing:**

```python
async def process_blog(job_id: str, url: str, formats: list[str], max_posts: int):
    # 1. discover_posts() - find all posts
    # 2. download_posts() - download content and images
    # 3. export_*() - generate requested formats
    # 4. shutil.make_archive() - create ZIP
```

### Frontend (`static/index.html`)

Single HTML file with:
- Tailwind CSS (via CDN)
- Brutalist design with e-reader cream/sepia colors
- Form: URL input, max posts (1-100), format checkboxes
- JavaScript: Form submission, status polling, download handling

---

## Dependencies

### Core Library
- `httpx` - Async HTTP client
- `beautifulsoup4` + `lxml` - HTML parsing
- `ebooklib` - EPUB generation
- `weasyprint` - PDF generation (requires system libs)
- `rich` - Console output and progress bars
- `typer` - CLI framework

### Web App
- `fastapi` - Web framework
- `uvicorn` - ASGI server

### System (for PDF generation)
- `libpango-1.0-0`, `libpangocairo-1.0-0` - Text rendering
- `libgdk-pixbuf-2.0-0` - Image handling
- `fonts-liberation` - Fonts

---

## Adding a New Platform

1. Create `blogpack/platforms/newplatform.py`:

```python
from .base import BlogPlatform, PostInfo, Article

class NewPlatform(BlogPlatform):
    name = "newplatform"

    def detect(self, html: str) -> bool:
        return "newplatform-marker" in html.lower()

    async def get_post_urls(self, base_url: str, client) -> list[PostInfo]:
        # Fetch sitemap or RSS, return list of PostInfo
        pass

    def extract_article(self, html: str, url: str) -> Article | None:
        # Parse HTML, extract title/author/date/content
        pass
```

2. Register in `blogpack/platforms/__init__.py`:

```python
from .newplatform import NewPlatform
PLATFORMS = [GhostPlatform(), SubstackPlatform(), WordPressPlatform(), NewPlatform()]
```

---

## Deployment

### Docker

```bash
docker build -t blogpack-web .
docker run -p 8000:8000 blogpack-web
```

### DigitalOcean App Platform

1. Push to GitHub
2. Create new App in DigitalOcean
3. Select repository, it will auto-detect Dockerfile
4. Deploy

### Environment Variables (optional)

- `MAX_CONCURRENT_JOBS` - Override default of 3
- `MAX_POSTS` - Override default of 100

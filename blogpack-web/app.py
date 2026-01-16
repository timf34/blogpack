"""Blogpack Web App - FastAPI backend."""

import asyncio
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directory to path for blogpack imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from blogpack.crawler import discover_posts
from blogpack.downloader import download_posts
from blogpack.exporters import export_html, export_epub, export_pdf

# Configuration
MAX_CONCURRENT_JOBS = 3
MAX_POSTS = 100
TEMP_DIR = Path("/tmp/blogpack") if sys.platform != "win32" else Path("C:/temp/blogpack")
JOB_EXPIRY_HOURS = 1

app = FastAPI(title="Blogpack", description="Pack blogs for offline reading")

# Mount static assets (for noise.png, etc.)
assets_path = Path(__file__).parent / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

# In-memory job tracking
jobs: dict[str, dict] = {}


class ProcessRequest(BaseModel):
    url: str
    formats: list[str] = ["pdf", "epub", "html"]
    max_posts: int = 100


class JobStatus(BaseModel):
    status: str  # "processing", "complete", "error"
    progress: str | None = None
    error: str | None = None
    download_ready: bool = False


def normalize_url(url: str) -> str:
    """Normalize blog URL."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not url.endswith("/"):
        url = url + "/"
    return url


def get_blog_title_from_url(url: str) -> str:
    """Extract a readable title from URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    # Remove common prefixes
    for prefix in ["www.", "blog.", "blogs."]:
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    return domain.replace(".", " ").title()


async def process_blog(job_id: str, url: str, formats: list[str], max_posts: int):
    """Background task to process a blog."""
    output_dir = TEMP_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        jobs[job_id]["progress"] = "Discovering posts..."

        # Discover posts
        platform, posts = await discover_posts(url)

        # Limit posts
        posts = posts[:min(max_posts, MAX_POSTS)]
        jobs[job_id]["progress"] = f"Downloading {len(posts)} posts..."

        # Download posts
        articles, image_map = await download_posts(
            url, posts, platform, include_images=True, output_dir=output_dir
        )

        if not articles:
            raise ValueError("No articles could be downloaded")

        # Get blog metadata
        blog_title = get_blog_title_from_url(url)
        blog_author = articles[0].author if articles else "Unknown"

        # Export to requested formats
        exported_files = []

        if "html" in formats:
            jobs[job_id]["progress"] = "Generating HTML..."
            html_path = export_html(articles, output_dir, url, image_map, blog_title)
            exported_files.append(html_path)

        if "epub" in formats:
            jobs[job_id]["progress"] = "Generating EPUB..."
            epub_path = export_epub(articles, output_dir, url, image_map, blog_title, blog_author)
            if epub_path:
                exported_files.append(epub_path)

        if "pdf" in formats:
            jobs[job_id]["progress"] = "Generating PDF..."
            pdf_path = export_pdf(articles, output_dir, url, image_map, blog_title, blog_author)
            if pdf_path:
                exported_files.append(pdf_path)

        # Create zip file
        jobs[job_id]["progress"] = "Creating download package..."
        zip_path = output_dir / "download"
        shutil.make_archive(str(zip_path), "zip", output_dir)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = None
        jobs[job_id]["download_ready"] = True

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["progress"] = None


def cleanup_old_jobs():
    """Remove jobs older than JOB_EXPIRY_HOURS."""
    cutoff = datetime.now() - timedelta(hours=JOB_EXPIRY_HOURS)
    to_remove = []
    for job_id, job in jobs.items():
        if job.get("created_at", datetime.now()) < cutoff:
            to_remove.append(job_id)
            # Clean up files
            job_dir = TEMP_DIR / job_id
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)

    for job_id in to_remove:
        del jobs[job_id]


@app.post("/process")
async def start_processing(request: ProcessRequest, background_tasks: BackgroundTasks):
    """Start processing a blog URL."""
    # Clean up old jobs first
    cleanup_old_jobs()

    # Check concurrent job limit
    running = sum(1 for j in jobs.values() if j["status"] == "processing")
    if running >= MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=503,
            detail="Too many users right now! Please come back later, or email timf34@gmail.com if this is something he should make just a little more scalable ;)"
        )

    # Validate request
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")

    if not request.formats:
        raise HTTPException(status_code=400, detail="At least one format must be selected")

    # Normalize and validate URL
    url = normalize_url(request.url)
    max_posts = min(max(1, request.max_posts), MAX_POSTS)

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "processing",
        "progress": "Starting...",
        "error": None,
        "download_ready": False,
        "created_at": datetime.now(),
    }

    # Start background processing
    background_tasks.add_task(process_blog, job_id, url, request.formats, max_posts)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str) -> JobStatus:
    """Get the status of a processing job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return JobStatus(
        status=job["status"],
        progress=job.get("progress"),
        error=job.get("error"),
        download_ready=job.get("download_ready", False),
    )


@app.get("/download/{job_id}")
async def download_file(job_id: str, background_tasks: BackgroundTasks):
    """Download the generated zip file."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Job not complete")

    zip_path = TEMP_DIR / job_id / "download.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Download file not found")

    # Schedule cleanup after download
    def cleanup():
        job_dir = TEMP_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        if job_id in jobs:
            del jobs[job_id]

    background_tasks.add_task(cleanup)

    return FileResponse(
        path=zip_path,
        filename="blogpack.zip",
        media_type="application/zip",
    )


# Serve the frontend
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main page."""
    static_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=static_path.read_text())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

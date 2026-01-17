"""Blogpack Web App - FastAPI backend."""

import asyncio
import gc
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import psutil
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
MAX_CONCURRENT_JOBS = 1  # Keep low for memory-constrained servers
MAX_POSTS = 50  # Reduced for 2GB RAM servers
TEMP_DIR = Path("/tmp/blogpack") if sys.platform != "win32" else Path("C:/temp/blogpack")
JOB_EXPIRY_HOURS = 1
MEMORY_THRESHOLD_PERCENT = 20  # Skip heavy exports if less than 20% memory available


def check_memory_available(threshold_percent: int = MEMORY_THRESHOLD_PERCENT) -> tuple[bool, float]:
    """Check if enough memory is available.

    Returns (is_ok, available_percent) where is_ok is True if available >= threshold.
    """
    mem = psutil.virtual_memory()
    available_percent = mem.available / mem.total * 100
    return available_percent >= threshold_percent, available_percent

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
    status: str  # "queued", "processing", "complete", "error"
    progress: str | None = None
    error: str | None = None
    download_ready: bool = False
    queue_position: int | None = None  # Position in queue (1 = next up)
    queue_total: int = 0  # Total jobs waiting + processing


class QueueInfo(BaseModel):
    processing: int  # Currently processing
    queued: int  # Waiting in queue
    total: int  # Total active jobs
    your_position: int | None = None  # Your position if you have a job


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
        skipped_formats = []

        # HTML is lightweight, always attempt it
        if "html" in formats:
            jobs[job_id]["progress"] = "Generating HTML..."
            html_path = export_html(articles, output_dir, url, image_map, blog_title)
            exported_files.append(html_path)
            gc.collect()  # Clean up after each export

        # EPUB - medium memory usage, check before starting
        if "epub" in formats:
            mem_ok, mem_avail = check_memory_available()
            if mem_ok:
                jobs[job_id]["progress"] = "Generating EPUB..."
                epub_path = export_epub(articles, output_dir, url, image_map, blog_title, blog_author)
                if epub_path:
                    exported_files.append(epub_path)
                gc.collect()
            else:
                skipped_formats.append("EPUB")
                jobs[job_id]["progress"] = f"Skipping EPUB (low memory: {mem_avail:.0f}% free)..."

        # PDF - heaviest memory usage, check before starting
        if "pdf" in formats:
            mem_ok, mem_avail = check_memory_available()
            if mem_ok:
                jobs[job_id]["progress"] = "Generating PDF..."
                pdf_path = export_pdf(articles, output_dir, url, image_map, blog_title, blog_author)
                if pdf_path:
                    exported_files.append(pdf_path)
                gc.collect()
            else:
                skipped_formats.append("PDF")
                jobs[job_id]["progress"] = f"Skipping PDF (low memory: {mem_avail:.0f}% free)..."

        # Check if we have any exported files
        if not exported_files:
            raise ValueError("No formats could be exported - server memory too low. Try fewer posts.")

        # Create zip file
        jobs[job_id]["progress"] = "Creating download package..."
        zip_path = output_dir / "download"
        shutil.make_archive(str(zip_path), "zip", output_dir)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["download_ready"] = True

        # Set completion message with skipped format info
        if skipped_formats:
            jobs[job_id]["progress"] = f"Done! (Skipped {', '.join(skipped_formats)} due to low memory - try fewer posts)"
        else:
            jobs[job_id]["progress"] = None

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["progress"] = None
    finally:
        # Force garbage collection to free memory from WeasyPrint/BeautifulSoup
        gc.collect()
        # Process next queued job if any
        await process_next_queued_job()


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


def get_queue_stats() -> tuple[int, int, list[str]]:
    """Get queue statistics. Returns (processing_count, queued_count, queued_job_ids_in_order)."""
    processing = 0
    queued_jobs = []

    for job_id, job in jobs.items():
        if job["status"] == "processing":
            processing += 1
        elif job["status"] == "queued":
            queued_jobs.append((job_id, job.get("queued_at", job.get("created_at"))))

    # Sort queued jobs by queue time (oldest first)
    queued_jobs.sort(key=lambda x: x[1])
    queued_ids = [j[0] for j in queued_jobs]

    return processing, len(queued_ids), queued_ids


def get_queue_position(job_id: str) -> int | None:
    """Get position in queue for a job (1 = next up). Returns None if not queued."""
    if job_id not in jobs or jobs[job_id]["status"] != "queued":
        return None

    _, _, queued_ids = get_queue_stats()
    try:
        return queued_ids.index(job_id) + 1
    except ValueError:
        return None


async def process_next_queued_job():
    """Start processing the next job in queue if capacity available."""
    processing, _, queued_ids = get_queue_stats()

    if processing >= MAX_CONCURRENT_JOBS or not queued_ids:
        return

    # Get the next job to process
    next_job_id = queued_ids[0]
    job = jobs[next_job_id]

    # Update status and start processing
    job["status"] = "processing"
    job["progress"] = "Starting..."

    # Start the background task
    asyncio.create_task(process_blog(
        next_job_id,
        job["url"],
        job["formats"],
        job["max_posts"]
    ))


@app.post("/process")
async def start_processing(request: ProcessRequest, background_tasks: BackgroundTasks):
    """Start processing a blog URL."""
    # Clean up old jobs first
    cleanup_old_jobs()

    # Validate request
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")

    if not request.formats:
        raise HTTPException(status_code=400, detail="At least one format must be selected")

    # Normalize and validate URL
    url = normalize_url(request.url)
    max_posts = min(max(1, request.max_posts), MAX_POSTS)

    # Check if we can start immediately or need to queue
    processing, queued, _ = get_queue_stats()
    now = datetime.now()

    job_id = str(uuid.uuid4())

    if processing < MAX_CONCURRENT_JOBS:
        # Can start immediately
        jobs[job_id] = {
            "status": "processing",
            "progress": "Starting...",
            "error": None,
            "download_ready": False,
            "created_at": now,
            "url": url,
            "formats": request.formats,
            "max_posts": max_posts,
        }
        # Start background processing
        background_tasks.add_task(process_blog, job_id, url, request.formats, max_posts)
    else:
        # Add to queue
        jobs[job_id] = {
            "status": "queued",
            "progress": None,
            "error": None,
            "download_ready": False,
            "created_at": now,
            "queued_at": now,
            "url": url,
            "formats": request.formats,
            "max_posts": max_posts,
        }

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str) -> JobStatus:
    """Get the status of a processing job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    processing, queued, _ = get_queue_stats()

    return JobStatus(
        status=job["status"],
        progress=job.get("progress"),
        error=job.get("error"),
        download_ready=job.get("download_ready", False),
        queue_position=get_queue_position(job_id),
        queue_total=processing + queued,
    )


@app.get("/queue")
async def get_queue() -> QueueInfo:
    """Get current queue status for display."""
    processing, queued, _ = get_queue_stats()
    return QueueInfo(
        processing=processing,
        queued=queued,
        total=processing + queued,
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

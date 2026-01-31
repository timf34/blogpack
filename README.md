# Blogpack

Download entire blogs for offline reading. Generates PDF, EPUB, and HTML with working internal links.

## Features

- Downloads all posts from a blog
- Preserves internal links between posts
- Downloads and embeds images
- Multiple output formats: EPUB (e-readers), HTML (browsers), PDF
- Supports Ghost, Substack, and WordPress blogs

## Installation

```bash
pip install blogpack
```

**Note:** PDF export requires additional system libraries. If PDF generation fails:
- Ubuntu/Debian: `sudo apt install libpango-1.0-0 libpangocairo-1.0-0`
- macOS: `brew install pango`
- Windows: Install GTK3 from MSYS2

EPUB and HTML exports work without these dependencies.

## CLI Usage

```bash
# Download a blog (generates all formats by default)
blogpack https://www.cold-takes.com/ -o ./cold-takes

# Generate only EPUB
blogpack https://www.cold-takes.com/ -f epub

# Limit to 50 posts
blogpack https://www.cold-takes.com/ -n 50

# Skip images for faster download
blogpack https://www.cold-takes.com/ --no-images
```

## Web App

A browser-based interface is included in `blogpack-web/`.

### Run Locally

```bash
cd blogpack-web
pip install -r requirements.txt
uvicorn app:app --reload
# Open http://localhost:8000
```

### Deploy with Docker

```bash
docker build -t blogpack-web .
docker run -p 8000:8000 blogpack-web
```

## Output Structure

```
output/
├── html/
│   ├── index.html           # Table of contents
│   ├── post-slug.html       # Individual posts
│   └── images/              # Downloaded images
├── blog-archive.epub        # For e-readers
└── blog-archive.pdf         # Single PDF
```

## Supported Platforms

| Platform | Status |
|----------|--------|
| Ghost | Supported |
| Substack | Supported |
| WordPress | Supported |

## Documentation

See [CLAUDE.md](CLAUDE.md) for detailed codebase documentation.

## License

GPL-3.0 - See [LICENSE](LICENSE) for details.

## Links

- GitHub: https://github.com/timf34/blogpack
- PyPI: https://pypi.org/project/blogpack/

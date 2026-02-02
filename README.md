# Blogpack

*Blog → Book!*

Download entire blogs for offline reading. Generates PDF, EPUB, and HTML with working internal links and embedded images.

Absolutely ideal for long flights, distraction free reading, digital detoxes, or pretending you'll finally catch up on that Substack.

Works with Substack, Ghost and Wordpress blogs. 

## Installation

```bash
pip install blogpack
```

**Note:** PDF export requires additional system libraries. If PDF generation fails:
- Ubuntu/Debian: `sudo apt install libpango-1.0-0 libpangocairo-1.0-0`
- macOS: `brew install pango`
- Windows: Install GTK3 from MSYS2

EPUB and HTML exports work without these dependencies.

## Usage

```bash
blogpack https://www.cold-takes.com/
```

Downloads the blog to `./cold-takes/` with HTML, EPUB, and PDF formats.

### Options

```bash
blogpack https://example.com/ -o ./my-folder   # Custom output directory
blogpack https://example.com/ -f epub          # Only generate EPUB
blogpack https://example.com/ -n 50            # Limit to 50 posts
blogpack https://example.com/ --no-images      # Skip images
blogpack https://example.com/ --no-verify-ssl  # Disable SSL verification
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
<blog-name>/                  # Derived from blog URL
├── html/
│   ├── index.html           # Table of contents
│   ├── post-slug.html       # Individual posts
│   └── images/              # Downloaded images
├── <blog-name>-archive.epub # For e-readers
└── <blog-name>-archive.pdf  # Single PDF
```

## License

GPL-3.0 - See [LICENSE](LICENSE) for details.

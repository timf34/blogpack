# Blogpack Production Deployment

Optimized for low-memory VPS (2GB RAM, 1 vCPU).

## Migrating from Docker to Native

If you're currently running Blogpack with Docker and want to switch to native Python (saves ~100-200MB RAM):

### Step 1: Stop Docker

```bash
# Stop the blogpack container
docker stop $(docker ps -q --filter ancestor=blogpack) 2>/dev/null || true

# Optional: Stop Docker daemon entirely to free memory
sudo systemctl stop docker
sudo systemctl disable docker
```

### Step 2: Set up swap (if not already done)

```bash
# Check current swap
free -h

# If no swap exists, create 2GB:
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Optimize swappiness
echo "vm.swappiness=10" | sudo tee /etc/sysctl.d/99-blogpack.conf
sudo sysctl -p /etc/sysctl.d/99-blogpack.conf
```

### Step 3: Install system dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev shared-mime-info fonts-liberation
```

### Step 4: Set up Python environment

```bash
cd /path/to/blogpack
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r blogpack-web/requirements.txt
```

### Step 5: Create temp directory

```bash
sudo mkdir -p /tmp/blogpack
sudo chown $USER:$USER /tmp/blogpack
```

### Step 6: Install and configure systemd service

```bash
# Copy the service file
sudo cp deploy/blogpack.service /etc/systemd/system/

# Edit to match your paths
sudo nano /etc/systemd/system/blogpack.service
```

Update these lines in the service file to match your setup:
```ini
User=your-username
Group=your-username
WorkingDirectory=/path/to/blogpack/blogpack-web
Environment="PATH=/path/to/blogpack/venv/bin"
ExecStart=/path/to/blogpack/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 --limit-max-requests 100
```

Then enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable blogpack
sudo systemctl start blogpack
```

### Step 7: Update nginx (if needed)

If you already have nginx configured for your domain, just update the proxy target:

```bash
sudo nano /etc/nginx/sites-available/your-site
```

Make sure it proxies to `http://127.0.0.1:8000`:
```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Step 8: Verify

```bash
# Check service status
sudo systemctl status blogpack

# Check logs
sudo journalctl -u blogpack -f

# Test endpoint
curl http://localhost:8000/queue
```

---

## Quick Setup (Fresh Install)

```bash
# On your server
sudo ./setup.sh
```

## Manual Commands

```bash
# Service management
sudo systemctl start blogpack
sudo systemctl stop blogpack
sudo systemctl restart blogpack
sudo systemctl status blogpack

# View logs
sudo journalctl -u blogpack -f

# Check memory usage
free -h
htop
```

## Memory Optimizations Applied

| Setting | Value | Why |
|---------|-------|-----|
| MAX_CONCURRENT_JOBS | 1 | One PDF at a time prevents OOM |
| MAX_POSTS | 50 | Reduced from 100 to limit memory per job |
| Swap | 2GB | Safety net for memory spikes |
| Swappiness | 10 | Prefer RAM, use swap only when needed |
| MemoryMax | 1800MB | Systemd kills process before OOM killer |
| gc.collect() | After each job | Frees WeasyPrint/BeautifulSoup memory |
| Memory checks | Before EPUB/PDF | Skips heavy exports if <20% RAM free |
| --limit-max-requests | 100 | Worker restarts to clear memory leaks |

## Compared to Docker

Running without Docker saves ~100-200MB RAM:
- No Docker daemon overhead
- No container runtime layer
- Direct process management

## Queue System

The app now queues requests instead of rejecting them:
- Users see their position in queue
- Jobs process one at a time
- Automatic progression when jobs complete
- Visual feedback with "Server ready" / "1 job processing" status

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
sudo journalctl -u blogpack -n 50

# Try running manually to see errors
cd /path/to/blogpack/blogpack-web
source ../venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Memory issues
```bash
# Check current memory
free -h

# Check if swap is active
swapon --show

# Monitor memory during job
watch -n 1 free -h
```

### Port already in use
```bash
# Find what's using port 8000
sudo lsof -i :8000

# Kill if needed
sudo kill -9 <PID>
```

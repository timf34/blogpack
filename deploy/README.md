# Blogpack Production Deployment

Optimized for low-memory VPS (2GB RAM, 1 vCPU).

## Quick Setup

```bash
# On your server
sudo ./setup.sh
```

## What the setup does

1. **Creates 2GB swap** - Prevents OOM kills during PDF generation
2. **Installs system deps** - Python 3.11, WeasyPrint dependencies, nginx
3. **Creates Python venv** - Isolated environment at `/opt/blogpack/venv`
4. **Installs systemd service** - Auto-restart, memory limits
5. **Configures nginx** - Reverse proxy with timeouts

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
| Swap | 2GB | Safety net for memory spikes |
| Swappiness | 10 | Prefer RAM, use swap only when needed |
| MemoryMax | 1800MB | Systemd kills process before OOM killer |
| gc.collect() | After each job | Frees WeasyPrint/BeautifulSoup memory |
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

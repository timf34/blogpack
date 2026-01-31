#!/bin/bash
# Blogpack Deployment Script for Ubuntu/Debian
# Run as root or with sudo

set -e

echo "=== Blogpack Production Setup ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup.sh)"
    exit 1
fi

# 1. Setup swap (2GB recommended for 2GB RAM droplet)
echo "[1/6] Setting up 2GB swap..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap created and enabled"
else
    echo "Swap already exists, skipping"
fi

# Optimize swap behavior for low-memory server
echo "vm.swappiness=10" > /etc/sysctl.d/99-blogpack.conf
sysctl -p /etc/sysctl.d/99-blogpack.conf

# 2. Install system dependencies
echo ""
echo "[2/6] Installing system dependencies..."
apt-get update
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    nginx

# 3. Create application directory and user setup
echo ""
echo "[3/6] Setting up application directory..."
mkdir -p /opt/blogpack
mkdir -p /tmp/blogpack
chown www-data:www-data /tmp/blogpack

# Copy application files (adjust source path as needed)
if [ -d "/home/user/blogpack" ]; then
    cp -r /home/user/blogpack/* /opt/blogpack/
fi

# 4. Create Python virtual environment and install dependencies
echo ""
echo "[4/6] Setting up Python environment..."
cd /opt/blogpack
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r blogpack-web/requirements.txt

# Set ownership
chown -R www-data:www-data /opt/blogpack

# 5. Install systemd service
echo ""
echo "[5/6] Installing systemd service..."
cp /opt/blogpack/deploy/blogpack.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable blogpack
systemctl start blogpack

# 6. Configure nginx (optional reverse proxy)
echo ""
echo "[6/6] Configuring nginx..."
cat > /etc/nginx/sites-available/blogpack << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/blogpack /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Blogpack is now running!"
echo "  - App: http://your-server-ip"
echo "  - Status: systemctl status blogpack"
echo "  - Logs: journalctl -u blogpack -f"
echo ""
echo "Memory optimization applied:"
echo "  - Swap: 2GB"
echo "  - Max concurrent jobs: 1"
echo "  - Worker memory limit: 1800MB"
echo "  - Swappiness: 10 (prefer RAM)"

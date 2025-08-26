#!/bin/bash
set -e

# SPRAXXX VPN Portal Deployment Script
# This script deploys the VPN portal to the server

echo "🚀 Starting SPRAXXX VPN Portal Deployment..."

# Configuration
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/opt/dcvpn"
NGINX_CONFIG="/etc/nginx/sites-available/dcvpn"
NGINX_ENABLED="/etc/nginx/sites-enabled/dcvpn"
SYSTEMD_SERVICE="/etc/systemd/system/dcvpn.service"
CLIENTS_DIR="/var/www/wg/clients"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

echo "📂 Setting up directories..."

# Create target directory
mkdir -p "$TARGET_DIR"
mkdir -p "$CLIENTS_DIR"

# Set proper ownership
chown -R www-data:www-data "$CLIENTS_DIR"
chmod 755 "$CLIENTS_DIR"

echo "📋 Copying application files..."

# Copy application files
cp "$REPO_DIR/app.py" "$TARGET_DIR/"
cp "$REPO_DIR/requirements.txt" "$TARGET_DIR/"
cp -r "$REPO_DIR/site" "$TARGET_DIR/"

# Set proper ownership for application files
chown -R www-data:www-data "$TARGET_DIR"

echo "🐍 Installing Python dependencies..."

# Install Python dependencies
cd "$TARGET_DIR"
pip3 install -r requirements.txt

echo "⚙️  Installing systemd service..."

# Install systemd service
cp "$REPO_DIR/systemd/dcvpn.service" "$SYSTEMD_SERVICE"
systemctl daemon-reload

echo "🌐 Configuring Nginx..."

# Install nginx configuration
cp "$REPO_DIR/nginx.conf" "$NGINX_CONFIG"

# Enable the site
ln -sf "$NGINX_CONFIG" "$NGINX_ENABLED"

# Remove default nginx site if it exists
if [[ -f "/etc/nginx/sites-enabled/default" ]]; then
    rm -f "/etc/nginx/sites-enabled/default"
fi

# Test nginx configuration
nginx -t

echo "🔄 Restarting services..."

# Stop services if running
systemctl stop dcvpn 2>/dev/null || true
systemctl stop nginx 2>/dev/null || true

# Start and enable services
systemctl enable dcvpn
systemctl start dcvpn

systemctl enable nginx
systemctl start nginx

echo "✅ Checking service status..."

# Check service status
sleep 3

if systemctl is-active --quiet dcvpn; then
    echo "✅ DCVPN service is running"
else
    echo "❌ DCVPN service failed to start"
    systemctl status dcvpn
    exit 1
fi

if systemctl is-active --quiet nginx; then
    echo "✅ Nginx service is running"
else
    echo "❌ Nginx service failed to start"
    systemctl status nginx
    exit 1
fi

# Test API endpoint
echo "🧪 Testing API endpoint..."
sleep 2

if curl -f -s http://localhost/health > /dev/null; then
    echo "✅ API health check passed"
else
    echo "⚠️  API health check failed - service may still be starting"
fi

echo "🎉 Deployment completed successfully!"
echo ""
echo "📊 Service Status:"
echo "   DCVPN API: $(systemctl is-active dcvpn)"
echo "   Nginx:     $(systemctl is-active nginx)"
echo ""
echo "🌍 Your VPN portal is now available at:"
echo "   http://$(hostname -I | awk '{print $1}')"
echo "   http://localhost (if testing locally)"
echo ""
echo "📝 Useful commands:"
echo "   View logs:    journalctl -u dcvpn -f"
echo "   Restart API:  systemctl restart dcvpn"
echo "   Restart web:  systemctl restart nginx"
echo "   Check status: systemctl status dcvpn nginx"
#!/bin/bash
set -euo pipefail

# deploy.sh - Idempotent deployment script for DCVPN portal

DEPLOY_ROOT="/opt/dcvpn"
SERVICE_NAME="dcvpn"
DOMAIN="vpn.spraxxx.net"

echo "=== DCVPN Portal Deployment ==="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Create deployment directory
echo "Creating deployment directory..."
mkdir -p "$DEPLOY_ROOT"

# Copy application files
echo "Copying application files..."
cp app.py requirements.txt .env.example "$DEPLOY_ROOT/"
cp -r site "$DEPLOY_ROOT/"

# Copy systemd service
echo "Installing systemd service..."
cp systemd/dcvpn.service /etc/systemd/system/
systemctl daemon-reload

# Install Python dependencies
echo "Installing Python dependencies..."
cd "$DEPLOY_ROOT"
pip3 install -r requirements.txt

# Create .env file if it doesn't exist
if [[ ! -f "$DEPLOY_ROOT/.env" ]]; then
    echo "Creating default .env file..."
    cp .env.example .env
    echo "⚠️  Please edit $DEPLOY_ROOT/.env with your configuration"
fi

# Create nginx configuration
echo "Setting up nginx configuration..."
PUBLIC_ROOT=$(grep "^PUBLIC_ROOT=" "$DEPLOY_ROOT/.env" | cut -d'=' -f2 || echo "/var/www/wg/clients")
sed "s|PUBLIC_ROOT|$PUBLIC_ROOT|g" nginx.conf > /etc/nginx/sites-available/dcvpn.conf

# Enable nginx site
if [[ ! -L /etc/nginx/sites-enabled/dcvpn.conf ]]; then
    ln -s /etc/nginx/sites-available/dcvpn.conf /etc/nginx/sites-enabled/
fi

# Test nginx configuration
echo "Testing nginx configuration..."
if nginx -t; then
    echo "✓ Nginx configuration is valid"
else
    echo "✗ Nginx configuration test failed"
    exit 1
fi

# Add rate limiting zone to nginx.conf if not present
if ! grep -q "limit_req_zone" /etc/nginx/nginx.conf; then
    echo "⚠️  Adding rate limiting zone to nginx.conf"
    sed -i '/http {/a\    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;' /etc/nginx/nginx.conf
fi

# Create public root directory
mkdir -p "$PUBLIC_ROOT"
chown www-data:www-data "$PUBLIC_ROOT"
chmod 755 "$PUBLIC_ROOT"

# Setup SSL certificates with certbot (non-fatal)
echo "Setting up SSL certificates..."
if command -v certbot >/dev/null 2>&1; then
    if [[ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
        echo "Obtaining SSL certificate for $DOMAIN..."
        certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@spraxxx.net || {
            echo "⚠️  Failed to obtain SSL certificate. Manual configuration required."
        }
    else
        echo "✓ SSL certificate already exists"
    fi
else
    echo "⚠️  certbot not installed. SSL certificates must be configured manually."
fi

# Enable and start services
echo "Starting services..."
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl reload nginx

# Check service status
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✓ $SERVICE_NAME service is running"
else
    echo "✗ $SERVICE_NAME service failed to start"
    systemctl status "$SERVICE_NAME"
    exit 1
fi

echo "=== Deployment Complete ==="
echo "Portal URL: https://$DOMAIN"
echo "Service logs: journalctl -u $SERVICE_NAME -f"
echo ""
echo "Next steps:"
echo "1. Edit $DEPLOY_ROOT/.env with your configuration"
echo "2. Set up WireGuard server configuration"
echo "3. Restart dcvpn service: systemctl restart $SERVICE_NAME"
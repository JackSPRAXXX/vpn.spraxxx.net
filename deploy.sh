#!/bin/bash
set -euo pipefail

# DCVPN v1.1 Deployment Script
# Idempotent deployment for production VPN portal

DOMAIN="${1:-vpn.spraxxx.net}"
PUBLIC_ROOT="/var/www/wg/clients"
APP_DIR="/opt/dcvpn"
USER="spraxxxvpn"

echo "🚀 Starting DCVPN v1.1 deployment for $DOMAIN"

# Create user if not exists
if ! id "$USER" &>/dev/null; then
    echo "📝 Creating user $USER"
    sudo useradd -r -s /bin/false -d "$APP_DIR" "$USER"
fi

# Create directories
echo "📁 Setting up directories"
sudo mkdir -p "$APP_DIR" "$PUBLIC_ROOT" /etc/wireguard/peers.d
sudo chown "$USER:$USER" "$APP_DIR" "$PUBLIC_ROOT"
sudo chmod 755 "$PUBLIC_ROOT"

# Install system dependencies
echo "📦 Installing system dependencies"
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv nginx wireguard-tools certbot python3-certbot-nginx

# Set up Python environment
echo "🐍 Setting up Python environment"
sudo -u "$USER" python3 -m venv "$APP_DIR/venv"
sudo cp requirements.txt "$APP_DIR/"
sudo chown "$USER:$USER" "$APP_DIR/requirements.txt"
sudo -u "$USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# Copy application files
echo "📋 Copying application files"
sudo cp app.py "$APP_DIR/"
sudo chown "$USER:$USER" "$APP_DIR/app.py"

# Set up environment file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚙️ Creating environment file"
    sudo cp .env.example "$APP_DIR/.env"
    sudo chown "$USER:$USER" "$APP_DIR/.env"
    sudo chmod 600 "$APP_DIR/.env"
    
    # Generate secure admin token
    ADMIN_TOKEN=$(openssl rand -base64 32)
    sudo sed -i "s/ADMIN_TOKEN=change-me/ADMIN_TOKEN=$ADMIN_TOKEN/" "$APP_DIR/.env"
    sudo sed -i "s/ENDPOINT_HOST=vpn.spraxxx.net/ENDPOINT_HOST=$DOMAIN/" "$APP_DIR/.env"
    
    echo "🔑 Generated admin token: $ADMIN_TOKEN"
    echo "Please save this token securely!"
fi

# Configure nginx
echo "🌐 Configuring nginx"
sudo cp nginx.conf /etc/nginx/sites-available/dcvpn
sudo sed -i "s/VPN_SERVER_DOMAIN_PLACEHOLDER/$DOMAIN/g" /etc/nginx/sites-available/dcvpn
sudo sed -i "s|PUBLIC_ROOT_PLACEHOLDER|$PUBLIC_ROOT|g" /etc/nginx/sites-available/dcvpn

# Add rate limiting to nginx.conf if not present
if ! grep -q "limit_req_zone.*api_burst" /etc/nginx/nginx.conf; then
    echo "📊 Adding rate limiting to nginx.conf"
    sudo sed -i '/http {/a\\tlimit_req_zone $binary_remote_addr zone=api_burst:10m rate=10r/m;' /etc/nginx/nginx.conf
fi

sudo ln -sf /etc/nginx/sites-available/dcvpn /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Copy site files
echo "🎨 Setting up web interface"
sudo mkdir -p /var/www/html
sudo cp site/index.html /var/www/html/
sudo chown www-data:www-data /var/www/html/index.html

# Test nginx configuration
sudo nginx -t

# Get SSL certificate
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "🔒 Obtaining SSL certificate"
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN" || true
fi

# Install systemd service
echo "⚙️ Installing systemd service"
sudo cp systemd/dcvpn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dcvpn
sudo systemctl enable nginx

# Start services
echo "🎯 Starting services"
sudo systemctl restart nginx
sudo systemctl restart dcvpn

# Health check
echo "🔍 Performing health check"
sleep 3
if curl -f http://localhost:8000/ >/dev/null 2>&1; then
    echo "✅ DCVPN API is healthy"
else
    echo "❌ DCVPN API health check failed"
    sudo systemctl status dcvpn
    exit 1
fi

if sudo nginx -t >/dev/null 2>&1; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Nginx configuration test failed"
    exit 1
fi

echo ""
echo "🎉 DCVPN v1.1 deployment completed successfully!"
echo ""
echo "🔗 Access your VPN portal at: https://$DOMAIN"
echo "🔑 Admin token: $(sudo grep ADMIN_TOKEN $APP_DIR/.env | cut -d= -f2)"
echo ""
echo "📋 Next steps:"
echo "  1. Configure your WireGuard server interface"
echo "  2. Ensure sudoers allows $USER to run wg commands"
echo "  3. Test client creation via the web interface"
echo ""
echo "📖 Documentation: https://github.com/JackSPRAXXX/vpn.spraxxx.net"
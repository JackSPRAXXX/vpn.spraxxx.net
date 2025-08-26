#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/dcvpn"
WWW_DIR="/var/www/wg"

sudo dnf -y install git python3-pip nginx qrencode || true

sudo mkdir -p "$REPO_DIR" "$WWW_DIR/clients"
sudo chown -R root:root "$WWW_DIR"
sudo chmod -R 755 "$WWW_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
  sudo git clone https://github.com/<YOUR-USER>/<YOUR-REPO>.git "$REPO_DIR"
else
  cd "$REPO_DIR" && sudo git pull --ff-only
fi

cd "$REPO_DIR"
sudo python3 -m pip install --upgrade pip
sudo pip3 install -r requirements.txt

# Copy site
sudo mkdir -p "$WWW_DIR"
sudo cp -r site/* "$WWW_DIR/"

# Systemd unit
sudo cp systemd/dcvpn.service /etc/systemd/system/dcvpn.service
sudo systemctl daemon-reload
sudo systemctl enable --now dcvpn

# Nginx
sudo cp nginx.conf /etc/nginx/conf.d/vpn.spraxxx.net.conf
sudo systemctl enable --now nginx
sudo nginx -t
sudo systemctl restart nginx

echo "Deployed. Visit http://vpn.spraxxx.net/health"
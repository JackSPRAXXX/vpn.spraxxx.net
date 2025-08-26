#!/usr/bin/env python3
"""
SPRAXXX VPN Portal - FastAPI Backend
Minimal VPN configuration and QR code generation service
"""

import os
import uuid
import qrcode
import io
import base64
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.backends import default_backend

app = FastAPI(title="SPRAXXX VPN Portal", version="1.0.0")

# Configuration
CLIENTS_DIR = Path("/var/www/wg/clients")
SITE_DIR = Path("site")

# Mount static files
app.mount("/site", StaticFiles(directory=str(SITE_DIR)), name="site")

def generate_keys():
    """Generate WireGuard private and public key pair"""
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    # Convert to WireGuard base64 format
    private_b64 = base64.b64encode(private_pem).decode('utf-8')
    public_b64 = base64.b64encode(public_pem).decode('utf-8')
    
    return private_b64, public_b64

def allocate_ip():
    """Allocate next available IP address"""
    # Simple IP allocation starting from 10.0.0.2
    # In production, this should use proper IP management
    if not CLIENTS_DIR.exists():
        CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    existing_clients = list(CLIENTS_DIR.glob("*.conf"))
    next_ip = len(existing_clients) + 2  # Start from 10.0.0.2
    
    if next_ip > 254:
        raise HTTPException(status_code=507, detail="No available IP addresses")
    
    return f"10.0.0.{next_ip}"

def generate_config(client_id, client_ip, private_key):
    """Generate WireGuard client configuration"""
    config = f"""[Interface]
PrivateKey = {private_key}
Address = {client_ip}/24
DNS = 8.8.8.8

[Peer]
PublicKey = SERVER_PUBLIC_KEY_PLACEHOLDER
AllowedIPs = 0.0.0.0/0
Endpoint = vpn.spraxxx.net:51820
PersistentKeepalive = 25
"""
    return config

def generate_qr_code(config_text):
    """Generate QR code for configuration"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(config_text)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for web display
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

@app.get("/")
async def root():
    """Redirect to the main landing page"""
    return {"message": "SPRAXXX VPN Portal API", "docs": "/docs"}

@app.post("/new")
async def create_new_client():
    """
    Create a new VPN client configuration
    - Allocates new IP address
    - Generates WireGuard keys
    - Creates configuration file
    - Generates QR code
    - Returns URLs for download and QR display
    """
    try:
        # Generate unique client ID
        client_id = str(uuid.uuid4())[:8]
        
        # Allocate IP address
        client_ip = allocate_ip()
        
        # Generate keys
        private_key, public_key = generate_keys()
        
        # Generate configuration
        config_text = generate_config(client_id, client_ip, private_key)
        
        # Save configuration file
        config_filename = f"{client_id}.conf"
        config_path = CLIENTS_DIR / config_filename
        
        with open(config_path, 'w') as f:
            f.write(config_text)
        
        # Generate QR code
        qr_data = generate_qr_code(config_text)
        
        # Save QR code as image file
        qr_filename = f"{client_id}.png"
        qr_path = CLIENTS_DIR / qr_filename
        
        # Extract base64 data and save as PNG
        qr_base64 = qr_data.split(',')[1]
        qr_bytes = base64.b64decode(qr_base64)
        
        with open(qr_path, 'wb') as f:
            f.write(qr_bytes)
        
        # Return URLs
        base_url = "/clients"  # Nginx will serve this
        
        return {
            "client_id": client_id,
            "ip": client_ip,
            "conf_url": f"{base_url}/{config_filename}",
            "qr_url": f"{base_url}/{qr_filename}",
            "public_key": public_key
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create client: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "dcvpn"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
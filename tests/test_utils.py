"""Test utilities for DCVPN portal."""

import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

# Import the app module
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_test_env():
    """Create a test environment with temporary directories."""
    temp_dir = Path(tempfile.mkdtemp())
    public_root = temp_dir / "public"
    public_root.mkdir()
    
    wg_conf = temp_dir / "wg0.conf"
    wg_conf.write_text("""[Interface]
PrivateKey = test_private_key
Address = 10.66.66.1/24
ListenPort = 51820

[Peer]
PublicKey = existing_peer_key
AllowedIPs = 10.66.66.2/32
""")
    
    # Set environment variables
    env_vars = {
        'WG_IFACE': 'wg0',
        'WG_CONF': str(wg_conf),
        'V4_NET': '10.66.66.0/24',
        'ENDPOINT': 'test.example.com:51820',
        'DNS': '8.8.8.8',
        'PUBLIC_ROOT': str(public_root),
        'ADMIN_TOKEN': 'test_token',
        'RATE_LIMIT_PER_MIN': '100'
    }
    
    return temp_dir, env_vars

def mock_wg_commands():
    """Mock WireGuard command outputs."""
    def mock_run_cmd(cmd, input_text=None):
        if cmd == ['/usr/bin/wg', 'genkey']:
            return 'test_private_key'
        elif cmd == ['bash', '-c', 'echo "test_private_key" | /usr/bin/wg pubkey']:
            return 'test_public_key'
        elif cmd == ['/usr/bin/wg', 'genpsk']:
            return 'test_preshared_key'
        elif cmd == ['/usr/bin/wg', 'show', 'wg0', 'public-key']:
            return 'server_public_key'
        elif cmd == ['/usr/bin/wg', 'show', 'wg0', 'allowed-ips']:
            return 'test_public_key\t10.66.66.2/32'
        elif cmd == ['/usr/bin/wg', 'show', 'wg0', 'dump']:
            return """wg0\tserver_private\tserver_public\t51820\toff
test_public_key\ttest_preshared_key\t10.66.66.2/32\t(none)\t0\t0\t0"""
        elif cmd[0:3] == ['/usr/bin/sudo', '/usr/bin/wg', 'set']:
            return ''
        else:
            return ''
    
    return mock_run_cmd

@pytest.fixture
def test_client():
    """Create a test client with mocked environment."""
    temp_dir, env_vars = create_test_env()
    
    with patch.dict(os.environ, env_vars, clear=False):
        # Import app after setting environment
        from app import app
        
        with patch('app.run_cmd', side_effect=mock_wg_commands()):
            with TestClient(app) as client:
                yield client, temp_dir

def test_sanitize_name():
    """Test name validation."""
    from app import sanitize_name
    from fastapi import HTTPException
    
    # Valid names
    assert sanitize_name("alice-phone") == "alice-phone"
    assert sanitize_name("test.device") == "test.device"
    assert sanitize_name("user_laptop") == "user_laptop"
    assert sanitize_name("device123") == "device123"
    
    # Invalid names
    with pytest.raises(HTTPException):
        sanitize_name("invalid name")  # spaces not allowed
    
    with pytest.raises(HTTPException):
        sanitize_name("invalid@name")  # @ not allowed
    
    with pytest.raises(HTTPException):
        sanitize_name("")  # empty name
    
    with pytest.raises(HTTPException):
        sanitize_name("a" * 65)  # too long

def test_ip_harvesting():
    """Test IP address harvesting from multiple sources."""
    temp_dir, env_vars = create_test_env()
    
    with patch.dict(os.environ, env_vars, clear=False):
        from app import harvest_used_ips, load_alloc, save_alloc
        
        # Create test allocation
        alloc = {"test-device": {"ip": "10.66.66.3", "pubkey": "test_key"}}
        save_alloc(alloc)
        
        with patch('app.run_cmd', side_effect=mock_wg_commands()):
            used_ips = harvest_used_ips()
            
            # Should include IPs from allocations.json and wg runtime
            assert "10.66.66.3" in used_ips  # from allocations
            assert "10.66.66.2" in used_ips  # from wg runtime and config

def test_api_authentication(test_client):
    """Test API authentication."""
    client, temp_dir = test_client
    
    # Test without token
    response = client.post("/new", json={"name": "test-device"})
    assert response.status_code == 401
    
    # Test with wrong token
    response = client.post("/new", 
                          json={"name": "test-device"},
                          headers={"Authorization": "Bearer wrong_token"})
    assert response.status_code == 401
    
    # Test with correct token
    response = client.post("/new",
                          json={"name": "test-device"},
                          headers={"Authorization": "Bearer test_token"})
    assert response.status_code == 201

def test_health_endpoint(test_client):
    """Test health check endpoint."""
    client, temp_dir = test_client
    
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
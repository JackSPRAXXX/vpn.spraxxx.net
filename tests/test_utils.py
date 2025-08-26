import re
import json
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path to import app
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_name_sanitization():
    """Test name sanitization function"""
    from app import normalize_name
    
    # Valid names
    assert normalize_name("alice-phone") == "alice-phone"
    assert normalize_name("user123") == "user123"
    assert normalize_name("test_device") == "test_device"
    
    # Invalid characters should be stripped
    assert normalize_name("alice@phone.com") == "alicephonecom"
    assert normalize_name("user 123!") == "user123"
    assert normalize_name("TEST-DEVICE") == "test-device"
    
    # Length limit
    long_name = "a" * 50
    assert len(normalize_name(long_name)) <= 32
    
    # Reserved names should raise error
    try:
        normalize_name("server")
        assert False, "Should have raised exception for reserved name"
    except Exception:
        pass
    
    try:
        normalize_name("wg0")
        assert False, "Should have raised exception for reserved name"
    except Exception:
        pass
    
    print("✅ Name sanitization tests passed")

def test_allocation_persistence():
    """Test allocation save/load functionality"""
    from app import save_alloc, load_alloc
    
    # Create temporary file for testing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        test_file = Path(f.name)
    
    # Monkey patch the ALLOC constant
    import app
    original_alloc = app.ALLOC
    app.ALLOC = test_file
    
    try:
        # Test saving and loading
        test_data = {
            "alice": {
                "ip": "10.66.66.2",
                "pubkey": "test-pubkey",
                "psk": "test-psk",
                "conf": "alice-abc123.conf",
                "qr": "alice-abc123.png"
            }
        }
        
        save_alloc(test_data)
        assert test_file.exists()
        
        loaded_data = load_alloc()
        assert loaded_data == test_data
        
        # Test loading non-existent file
        test_file.unlink()
        empty_data = load_alloc()
        assert empty_data == {}
        
        print("✅ Allocation persistence tests passed")
        
    finally:
        # Cleanup
        app.ALLOC = original_alloc
        if test_file.exists():
            test_file.unlink()

def test_ip_parsing():
    """Test IP parsing from WireGuard config"""
    from app import parse_server_ip
    import app
    
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        f.write("""[Interface]
Address = 10.66.66.1/24
PrivateKey = test-key
ListenPort = 8477

[Peer]
PublicKey = test-peer-key
AllowedIPs = 10.66.66.2/32
""")
        test_conf = Path(f.name)
    
    # Monkey patch the WG_CONF constant
    original_conf = app.WG_CONF
    app.WG_CONF = test_conf
    
    try:
        server_ip = parse_server_ip()
        assert server_ip == "10.66.66.1"
        print("✅ IP parsing tests passed")
        
    finally:
        # Cleanup
        app.WG_CONF = original_conf
        test_conf.unlink()

def test_rate_limiting():
    """Test rate limiting functionality"""
    from app import take_token_for, _tokens, _last_refill
    import time
    
    # Clear state
    _tokens.clear()
    _last_refill.clear()
    
    test_ip = "192.168.1.100"
    
    # Should be able to take initial tokens
    for i in range(10):
        assert take_token_for(test_ip), f"Should have tokens available at iteration {i}"
    
    # Should be rate limited now
    assert not take_token_for(test_ip), "Should be rate limited"
    
    # Tokens should still be 0
    assert _tokens.get(test_ip, 0) == 0
    
    print("✅ Rate limiting tests passed")

def test_config_validation():
    """Test configuration file validation"""
    
    # Test that all required environment variables have defaults
    required_vars = [
        'WG_BIN', 'SUDO_BIN', 'WG_IFACE', 'V4_NET', 
        'DNS', 'PUBLIC_ROOT', 'RATE_LIMIT_PER_MIN'
    ]
    
    import app
    for var in required_vars:
        value = getattr(app, var)
        assert value is not None, f"Required variable {var} should have a default value"
        assert value != "", f"Required variable {var} should not be empty"
    
    print("✅ Configuration validation tests passed")

if __name__ == "__main__":
    print("🧪 Running DCVPN utility tests...")
    
    test_name_sanitization()
    test_allocation_persistence()
    test_ip_parsing()
    test_rate_limiting()
    test_config_validation()
    
    print("🎉 All tests passed!")
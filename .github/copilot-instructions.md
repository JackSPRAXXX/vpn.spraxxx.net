# SPRAXXX VPN Portal - SystemD Service Configuration

**ALWAYS follow these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

This repository contains systemd service configuration for the SPRAXXX VPN portal, a FastAPI-based web application that manages VPN access using WireGuard.

## Critical Repository Understanding

**IMPORTANT**: This repository contains ONLY the systemd service configuration file. There is NO buildable application code, tests, or build scripts in this repository. The actual VPN portal application is deployed separately.

## Repository Structure

```
/
├── README.md              # Minimal description
├── LICENSE               # Apache 2.0 license
└── systemd/
    └── dcvpn.service     # SystemD service configuration for VPN portal
```

## Working Effectively

### System Requirements Validation
- Python 3.12+ is available (`python3 --version`)
- SystemD 255+ is available (`systemctl --version`)
- pip3 is available for Python package management

### Validating SystemD Service Configuration
- Validate service file syntax: `systemd-analyze verify systemd/dcvpn.service`
- Check file format: `file systemd/dcvpn.service` (should be ASCII text)
- Both commands complete instantly (< 5 seconds)

### Repository Operations
- Clone and navigate: Standard git operations work normally
- No build process: There is nothing to build in this repository
- No tests: There are no tests to run
- No dependencies: No package.json, requirements.txt, or similar files

## VPN Portal Application Details

Based on the systemd service configuration (`systemd/dcvpn.service`):

### Application Architecture
- **Technology**: FastAPI web application running on Python 3
- **Server**: Uvicorn ASGI server
- **Port**: 8000 (localhost only)
- **Working Directory**: `/opt/dcvpn` (deployment location)
- **Dependencies**: WireGuard service (`wg-quick@wg0y.service`)

### Service Configuration
- **Service Name**: dcvpn.service
- **Description**: "SPRAXXX VPN portal (FastAPI)"
- **User/Group**: root/root
- **Restart Policy**: always
- **Network Dependencies**: Starts after network and WireGuard service

### Installation Commands (On Target Server)
```bash
# Copy service file to systemd directory
sudo cp systemd/dcvpn.service /etc/systemd/system/

# Reload systemd configuration
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable dcvpn.service

# Start the service
sudo systemctl start dcvpn.service

# Check service status
sudo systemctl status dcvpn.service
```

## Common Tasks

### Modifying Service Configuration
1. Edit `systemd/dcvpn.service` directly
2. Validate syntax: `systemd-analyze verify systemd/dcvpn.service`
3. Commit changes to repository
4. Deploy updated service file to target server
5. Reload systemd and restart service

### Repository Operations That Work
- `git status` - Check repository status
- `git log` - View commit history  
- `git diff` - See changes
- `systemd-analyze verify systemd/dcvpn.service` - Validate service file
- Standard file operations on service configuration

### Operations That Do NOT Work
- Building: No build process exists
- Testing: No tests exist
- Running locally: Application code not in repository
- Installing dependencies: No dependency files exist
- Linting: No linting configuration exists

## Key Files Reference

### systemd/dcvpn.service
```ini
[Unit]
Description=SPRAXXX VPN portal (FastAPI)
After=network.target wg-quick@wg0y.service

[Service]
WorkingDirectory=/opt/dcvpn
ExecStart=/usr/bin/python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
```

### README.md
```markdown
# vpn.spraxxx.net
First VPN
```

## Application Development Context

If you need to work on the actual VPN portal application:

### Expected Application Location
- **Deployment Path**: `/opt/dcvpn/`
- **Main Module**: `app:app` (suggests `app.py` with FastAPI app instance)
- **Framework**: FastAPI with uvicorn server
- **Dependencies**: Likely includes fastapi, uvicorn, and wireguard tools

### Development Workflow (Outside This Repository)
1. Develop FastAPI application separately
2. Deploy to `/opt/dcvpn/` on target server
3. Install Python dependencies (fastapi, uvicorn, etc.)
4. Use this repository's systemd service to manage the deployed application
5. Ensure WireGuard is configured and `wg-quick@wg0y.service` is operational

## Troubleshooting

### Service File Issues
- Syntax errors: Run `systemd-analyze verify systemd/dcvpn.service`
- Invalid characters: Ensure file is ASCII text format
- Path issues: Verify `/opt/dcvpn` exists on target server

### Common Questions
- **"Where is the application code?"** - Not in this repository, deployed separately to `/opt/dcvpn`
- **"How do I build this?"** - Nothing to build, this is configuration only
- **"Can I run this locally?"** - No, requires separate application deployment
- **"How do I test changes?"** - Deploy service file and test on target server with actual application

## Security Notes
- Service runs as root (required for VPN operations)
- Application binds to localhost only (127.0.0.1:8000)
- Depends on WireGuard service for VPN functionality
- Apache 2.0 licensed
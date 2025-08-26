# VPN Portal v1.1 Deployment Checklist

## Pre-Deployment Review

### Code Quality
- [ ] All Python code follows PEP 8 standards
- [ ] Security scan (bandit) shows no critical issues
- [ ] Unit tests pass for utility functions
- [ ] FastAPI application starts without errors
- [ ] Environment file is properly configured

### Security Validation
- [ ] Admin token is generated and stored securely
- [ ] Rate limiting is configured in nginx
- [ ] File permissions are set correctly (640 for client files)
- [ ] Absolute paths are used for wg and sudo binaries
- [ ] Input validation prevents injection attacks
- [ ] Bearer token authentication is implemented
- [ ] HTTPS is enforced with proper SSL configuration

### Infrastructure Setup
- [ ] Domain name is properly configured
- [ ] SSL certificate is obtained and valid
- [ ] Nginx configuration is tested and valid
- [ ] Systemd service is enabled and running
- [ ] WireGuard interface is configured
- [ ] User `spraxxxvpn` has proper sudo permissions for wg commands

### Application Configuration
- [ ] Environment variables are set in `/opt/dcvpn/.env`
- [ ] WireGuard interface name matches configuration
- [ ] Endpoint host and port are correct
- [ ] Public root directory exists and is writable
- [ ] Allocation file path is accessible

### Network & Firewall
- [ ] Port 443 (HTTPS) is open
- [ ] Port 8477 (WireGuard) is open
- [ ] Rate limiting zone is configured in nginx.conf
- [ ] Internal API port 8000 is not exposed externally

## Deployment Steps

### System Preparation
- [ ] Run `sudo ./deploy.sh [domain]` to execute deployment
- [ ] Verify system dependencies are installed
- [ ] Confirm Python virtual environment is created
- [ ] Check that all directories are created with correct permissions

### Service Configuration
- [ ] Systemd service is installed and enabled
- [ ] Service starts successfully: `sudo systemctl status dcvpn`
- [ ] Nginx configuration is deployed and tested
- [ ] SSL certificate is obtained and configured
- [ ] Web interface is accessible

### WireGuard Setup
- [ ] WireGuard server interface is configured
- [ ] Server private/public keys are generated
- [ ] Interface is up and running
- [ ] Sudo permissions are configured for spraxxxvpn user

## Post-Deployment Testing

### Health Checks
- [ ] API health endpoint responds: `curl https://domain.com/`
- [ ] Web interface loads correctly
- [ ] Admin authentication works with generated token

### Functional Testing
- [ ] Create test client configuration
- [ ] Verify QR code generation works
- [ ] Download configuration file successfully
- [ ] Check status endpoint shows created client
- [ ] Revoke test client successfully
- [ ] Verify client files are cleaned up after revocation

### Security Testing
- [ ] Unauthorized requests are rejected (401)
- [ ] Rate limiting prevents abuse
- [ ] File enumeration is prevented
- [ ] Client files have opaque names
- [ ] SSL/TLS configuration is secure

### Monitoring Setup
- [ ] Log files are accessible: `sudo journalctl -u dcvpn -f`
- [ ] Error handling is working correctly
- [ ] Performance is acceptable under load

## Production Readiness

### Documentation
- [ ] Admin token is documented securely
- [ ] Deployment procedure is documented
- [ ] Troubleshooting guide is available
- [ ] Backup procedures are established

### Maintenance
- [ ] Log rotation is configured
- [ ] SSL certificate auto-renewal is set up
- [ ] Update procedures are documented
- [ ] Monitoring alerts are configured

### Compliance
- [ ] Data retention policies are defined
- [ ] Access logs are configured appropriately
- [ ] Security policies are documented
- [ ] Incident response procedures are in place

## Sign-off

- [ ] Technical lead approval
- [ ] Security review completed
- [ ] Operations team notified
- [ ] Documentation updated
- [ ] Deployment completed successfully

**Deployment Date:** _______________  
**Deployed By:** _______________  
**Reviewed By:** _______________
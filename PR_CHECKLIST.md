# Pull Request Checklist

## Pre-submission Checklist
- [ ] **Code Review**: All code has been reviewed for security vulnerabilities
- [ ] **Dependencies**: All new dependencies are justified and from trusted sources
- [ ] **Environment**: `.env.example` updated with all required variables
- [ ] **Documentation**: README and deployment instructions updated
- [ ] **Tests**: All tests pass and new functionality is tested

## Security Checklist
- [ ] **Authentication**: Admin token validation implemented correctly
- [ ] **Rate Limiting**: Rate limiting configured and tested
- [ ] **Input Validation**: All user inputs properly sanitized
- [ ] **File Permissions**: Client files have restricted permissions (640)
- [ ] **Command Injection**: All subprocess calls use absolute paths and parameterized commands
- [ ] **SSL/TLS**: HTTPS enforced with proper security headers
- [ ] **Secrets**: No secrets committed to repository

## Functionality Checklist
- [ ] **Client Creation**: Can create WireGuard client configurations
- [ ] **QR Code Generation**: QR codes generated using Python qrcode library
- [ ] **IP Management**: IP addresses harvested from all sources (allocations, runtime, config)
- [ ] **Peer Persistence**: Peers persisted to peers.d or WG_CONF as appropriate
- [ ] **Client Revocation**: Can revoke clients and clean up all files
- [ ] **Status Reporting**: Status endpoint shows live peer information
- [ ] **File Cleanup**: Atomic writes and proper cleanup on failures

## Deployment Checklist
- [ ] **Systemd Service**: Service configured with environment file support
- [ ] **Nginx Configuration**: Rate limiting and security headers configured
- [ ] **SSL Certificates**: Certificate procurement handled gracefully
- [ ] **Directory Structure**: All required directories created with correct permissions
- [ ] **Idempotent Deployment**: Deploy script can be run multiple times safely

## Testing Checklist
- [ ] **Unit Tests**: Core functions tested
- [ ] **Integration Tests**: API endpoints tested
- [ ] **Security Tests**: Authentication and authorization tested
- [ ] **Error Handling**: Error conditions properly handled and tested
- [ ] **CI Pipeline**: All CI checks pass

## Documentation Checklist
- [ ] **API Documentation**: Endpoints documented
- [ ] **Configuration**: Environment variables documented
- [ ] **Deployment**: Step-by-step deployment guide provided
- [ ] **Security Notes**: Security considerations documented
- [ ] **Smoke Tests**: Basic functionality verification steps provided
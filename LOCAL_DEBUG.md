# Local Development & Debugging Guide

## Quick Start Development

### 1. Environment Setup
```bash
# Copy example environment file
cp example.env .env

# Edit configuration for your environment
vim .env
```

### 2. Development Workflow
```bash
# Start development environment
docker-compose up -d

# View logs in real-time
docker-compose logs -f sip-server

# Make code changes, then restart
docker-compose restart sip-server

# For major changes, rebuild
docker-compose down
docker-compose build sip-server
docker-compose up -d
```

### 3. Test Environment
```bash
# Run test suite with Docker Compose
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Run tests locally (requires Python environment)
python3 -m pytest src/tests/ -v
```

## Debugging Process

1. **Check container status**: `docker-compose ps`
2. **View logs**: `docker-compose logs -f sip-server`
3. **Check individual components** (database, API, WebSocket)
4. **Fix issues in priority order** (critical errors first)
5. **Validate with tests** after each fix

## Issue Priority Guidelines

**HIGH PRIORITY** (Fix immediately):
- Service startup failures
- Database connection issues
- Critical module loading errors
- Security vulnerabilities

**MEDIUM PRIORITY** (Fix after critical issues):
- Performance degradation
- Non-critical module warnings
- Configuration optimizations

**LOW PRIORITY** (Fix during maintenance):
- Unit test failures (non-blocking)
- Code style improvements
- Documentation updates

## Development Rules

**IMPORTANT**: When fixing issues, ensure changes don't break existing functionality.

### Before Making Changes
- Review existing code structure and dependencies thoroughly
- Identify potential side effects on other components
- Verify all edge cases are handled
- Check for race conditions in concurrent operations
- Ensure backward compatibility where needed

### For Each Change
- Provide complete implementations, not partial updates
- Include necessary imports and dependencies
- Handle all error cases and exceptions
- Include proper null checks and input validation
- Maintain current method signatures where possible
- Preserve existing behavior for dependent code

### Validation Requirements
- Verify solution meets all functional requirements
- Confirm it follows existing patterns and conventions
- Check performance implications
- Ensure thread safety if applicable
- Verify changes don't break existing interfaces

### Code Quality Standards
- Don't assume anything - verify all assumptions
- Provide production-ready code rather than examples
- Include complete methods/classes with proper context
- Focus on working, tested solutions

## Common Issues & Solutions

### RTPproxy Connection Failures
- Ensure RTP bridge starts before Kamailio
- Check port 12221 availability
- Verify RTPproxy protocol compliance

### Database Issues
- Confirm PostgreSQL service is ready
- Check table existence and permissions
- Validate connection strings

### Module Loading Errors
- Verify all required Kamailio modules are installed
- Check module dependencies
- Review configuration syntax

## Testing Commands

### Health Checks
```bash
# Check all services status
docker-compose ps

# Check API health endpoint
curl http://localhost:8080/health

# Check WebSocket endpoint
curl -H "Authorization: Bearer your_jwt_token" \
     -H "Upgrade: websocket" \
     http://localhost:8081/ws

# Test database connection
docker-compose exec sip-server python3 -c "
from src.utils.config import get_config
from src.models.database import get_database_url
print('Config loaded:', get_config().database.host)
print('Database URL:', get_database_url())
"
```

### API Testing
```bash
# Test configuration endpoint
curl http://localhost:8080/api/config

# Test call endpoints
curl -X POST http://localhost:8080/api/calls/initiate \
     -H "Content-Type: application/json" \
     -d '{"from_number": "+1234567890", "to_number": "+0987654321"}'

# Test SMS endpoints
curl -X POST http://localhost:8080/api/sms/send \
     -H "Content-Type: application/json" \
     -d '{"from_number": "+1234567890", "to_number": "+0987654321", "message": "Test"}'

# Get active calls
curl http://localhost:8080/api/calls/active
```

### Comprehensive Test Suite
```bash
# Run full test suite with Docker Compose
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Run specific test categories
python3 -m pytest src/tests/test_config.py -v
python3 -m pytest src/tests/test_integration.py -v
python3 -m pytest src/tests/unit/ -v

# Run tests with coverage
python3 -m pytest src/tests/ --cov=src --cov-report=html

# Test configuration loading
python3 -c "
from src.utils.config import ConfigManager, get_config
config = get_config()
print('✅ Configuration loaded successfully')
print(f'Database: {config.database.host}:{config.database.port}')
print(f'API Port: {config.api.port}')
print(f'WebSocket Port: {config.websocket.port}')
"
```

### Component Testing
```bash
# Test Call Manager
python3 -c "
from src.call_handling.call_manager import CallManager
from unittest.mock import AsyncMock
manager = CallManager(max_concurrent_calls=10, ai_websocket_manager=AsyncMock())
print('✅ CallManager initialized successfully')
"

# Test WebSocket Bridge
python3 -c "
from src.websocket.bridge import WebSocketBridge
bridge = WebSocketBridge('ws://localhost:8081/ws')
print('✅ WebSocketBridge initialized successfully')
"

# Test Audio Processor
python3 -c "
from src.audio.codecs import AudioProcessor
processor = AudioProcessor()
print('✅ AudioProcessor initialized successfully')
"
```

### Kamailio Testing
```bash
# Test Kamailio configuration
docker-compose exec sip-server kamailio -c -f /etc/kamailio/kamailio.cfg

# Check Kamailio process
docker-compose exec sip-server pgrep kamailio

# Monitor SIP traffic (if needed)
docker-compose exec sip-server tcpdump -i any port 5060 -n
```

## Emergency Recovery

If system becomes unstable:

1. **Full reset**: `docker compose down -v && docker compose build --no-cache sip-server && docker compose up -d`
2. **Check all services**: `docker compose ps`
3. **Review logs**: `docker compose logs -f`
4. **Fix critical errors** in order of severity
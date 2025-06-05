# Local Development & Debugging Guide

## Development Workflow

After making any changes to the codebase, follow this sequence:

```bash
docker compose down
docker compose build sip-server
docker compose up -d
```

## Debugging Process

1. **Check container status**: `docker compose ps`
2. **View logs**: `docker compose logs -f sip-server`
3. **Fix issues in priority order** (critical errors first)
4. **Rebuild and test** after each fix

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

```bash
# Check service health
docker compose exec sip-server curl -f http://localhost:8000/health

# Test Kamailio config
docker compose exec sip-server kamailio -c -f /etc/kamailio/kamailio.cfg

# Check RTP bridge status
docker compose exec sip-server netstat -tuln | grep 12221

# Run unit tests
docker compose exec sip-server python3 -m pytest src/tests/ -v

# Check database connection
docker compose exec sip-server python3 -c "from src.models.database import get_db_connection; print('DB OK' if get_db_connection() else 'DB FAIL')"
```

## Emergency Recovery

If system becomes unstable:

1. **Full reset**: `docker compose down -v && docker compose build --no-cache sip-server && docker compose up -d`
2. **Check all services**: `docker compose ps`
3. **Review logs**: `docker compose logs -f`
4. **Fix critical errors** in order of severity
# SIP Server Troubleshooting Guide

## Quick Diagnostics

Before diving into specific issues, run these validation scripts:

```bash
# Validate Docker environment BEFORE starting
./validate-docker.sh

# Check container health AFTER starting
docker-compose exec sip-server /app/scripts/health-check.sh
```

## Common Issues and Solutions

### 1. Container Stuck in "Created" State

**Symptoms:**
- Container shows as "Created" but never starts
- No logs appear when running `docker-compose logs`

**Causes & Solutions:**

1. **Missing DATABASE_URL**
   ```bash
   # Check if .env file exists
   ls -la .env
   
   # If missing, copy from example
   cp example.env .env
   
   # Ensure DATABASE_URL is set
   grep DATABASE_URL .env
   ```

2. **Large port ranges in Dockerfile**
   - Remove or reduce EXPOSE ranges like `10000-20000/udp`
   - Already fixed in current version

3. **Docker daemon issues**
   ```bash
   # Clean up and restart
   docker-compose down -v
   docker system prune -f
   docker-compose up --build
   ```

### 2. Database Connection Failures

**Error:** `ERROR:__main__:DATABASE_URL environment variable not set`

**Solution:**
```bash
# Add to .env file
echo "DATABASE_URL=postgresql://kamailio:kamailiopw@postgres:5432/kamailio" >> .env
```

**Error:** `Can't connect to PostgreSQL`

**Solutions:**
1. Ensure PostgreSQL container is healthy:
   ```bash
   docker-compose ps
   # Should show postgres as "healthy"
   ```

2. Wait for PostgreSQL to be ready:
   ```bash
   docker-compose up -d postgres
   # Wait 10 seconds
   sleep 10
   docker-compose up sip-server
   ```

### 3. Port Conflicts

**Error:** `bind: address already in use`

**Check which ports are in use:**
```bash
# macOS
lsof -i :5060
lsof -i :8080
lsof -i :8081
lsof -i :5432

# Linux
netstat -tlnp | grep -E '5060|8080|8081|5432'
```

**Solutions:**
1. Stop conflicting services
2. Change ports in .env file:
   ```
   API_PORT=8090
   WEBSOCKET_PORT=8091
   ```

### 4. Python Import Errors

**Error:** `ModuleNotFoundError`

**Solutions:**
1. Rebuild with no cache:
   ```bash
   docker-compose build --no-cache sip-server
   ```

2. Check requirements.txt is complete
3. Verify PYTHONPATH is set correctly

### 5. Supervisor Not Found

**Error:** `supervisord not found`

**Solution:**
Already fixed - startup.sh now checks multiple locations

### 6. RTPProxy Warnings

**Warning:** `rtpproxy: can't send command to a RTP proxy`

**This is expected** - the system uses a custom RTP-WebSocket bridge instead of rtpproxy.

### 7. Container Health Check Failures

**Check what's failing:**
```bash
docker-compose exec sip-server /app/scripts/health-check.sh
```

**Common fixes:**
- Wait longer for services to start (90s start period)
- Check individual service logs
- Verify all environment variables are set

## Debugging Commands

### View Real-time Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f sip-server

# With timestamps
docker-compose logs -f --timestamps sip-server
```

### Access Container Shell
```bash
# While running
docker-compose exec sip-server /bin/bash

# If crashed
docker-compose run --rm sip-server /bin/bash
```

### Check Service Status
```bash
# Inside container
supervisorctl status
ps aux | grep -E 'kamailio|python'
```

### Test Individual Components
```bash
# Test API
curl http://localhost:8080/health

# Test WebSocket
curl http://localhost:8081/

# Test SIP (requires SIP client)
# Use a SIP testing tool like sipp or your SIP phone
```

## Prevention

1. **Always validate before starting:**
   ```bash
   ./validate-docker.sh && docker-compose up
   ```

2. **Use the startup validation:**
   The container now runs validation automatically on startup

3. **Monitor health:**
   ```bash
   watch -n 5 'docker-compose ps'
   ```

4. **Clean up regularly:**
   ```bash
   docker-compose down -v
   docker system prune -f
   ```

## Getting Help

If issues persist after trying these solutions:

1. Run the validation script and save output:
   ```bash
   ./validate-docker.sh > validation.log 2>&1
   ```

2. Collect container logs:
   ```bash
   docker-compose logs > container.log 2>&1
   ```

3. Check system resources:
   ```bash
   docker system df
   docker stats --no-stream
   ```

4. Include this information when reporting issues
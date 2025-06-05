#!/bin/bash
# Health check script with detailed error reporting

# Don't exit on error - we want to report what's wrong
set +e

HEALTHY=true
ISSUES=""

# Function to check a service
check_service() {
    local name=$1
    local check_cmd=$2
    
    if eval "$check_cmd" &>/dev/null; then
        echo "✓ $name is healthy"
    else
        echo "✗ $name is not healthy"
        ISSUES="$ISSUES\n  - $name check failed"
        HEALTHY=false
    fi
}

echo "=== Container Health Check ==="

# 1. Check API server
check_service "API Server" "curl -f http://localhost:${API_PORT:-8080}/health"

# 2. Check WebSocket server
check_service "WebSocket Server" "curl -f http://localhost:${WEBSOCKET_PORT:-8081}/"

# 3. Check Kamailio process
check_service "Kamailio" "pgrep kamailio"

# 4. Check Python integration
check_service "SIP Integration" "pgrep -f 'python.*main_integration'"

# 5. Check database connectivity
check_service "Database Connection" "pg_isready -h ${DB_HOST:-postgres} -p ${DB_PORT:-5432}"

# Report results
if [ "$HEALTHY" = true ]; then
    echo -e "\n✅ All services are healthy"
    exit 0
else
    echo -e "\n❌ Health check failed. Issues:$ISSUES"
    
    # Additional diagnostics
    echo -e "\nDiagnostics:"
    echo "- Processes: $(ps aux | grep -E 'kamailio|python' | grep -v grep | wc -l) running"
    echo "- Memory: $(free -m | grep Mem | awk '{print $3"/"$2" MB used"}')"
    echo "- Disk: $(df -h /app | tail -1 | awk '{print $5" used"}')"
    
    exit 1
fi
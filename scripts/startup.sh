#!/bin/bash
set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Better error handling with context
error_handler() {
    local line_no=$1
    echo -e "${RED}[ERROR] Script failed at line $line_no${NC}" >&2
    echo -e "${RED}[ERROR] Last command: ${BASH_COMMAND}${NC}" >&2
    echo -e "${RED}[ERROR] Exit code: $?${NC}" >&2
    
    # Provide helpful context based on where it failed
    if [ $line_no -lt 50 ]; then
        echo -e "${YELLOW}[HINT] This appears to be a database connection issue.${NC}" >&2
        echo -e "${YELLOW}[HINT] Check DATABASE_URL and ensure PostgreSQL is running.${NC}" >&2
    elif [ $line_no -lt 100 ]; then
        echo -e "${YELLOW}[HINT] This appears to be a Python import issue.${NC}" >&2
        echo -e "${YELLOW}[HINT] Check if all requirements are installed.${NC}" >&2
    else
        echo -e "${YELLOW}[HINT] This appears to be a service startup issue.${NC}" >&2
        echo -e "${YELLOW}[HINT] Check logs above for more details.${NC}" >&2
    fi
    
    exit 1
}

trap 'error_handler $LINENO' ERR

# Function to log with color
log_info() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

log_error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
}

# Run validation first
log_info "Running startup validation..."
if [ -f /app/scripts/validate-startup.sh ]; then
    /app/scripts/validate-startup.sh || {
        log_error "Validation failed! Please fix the issues above before proceeding."
        exit 1
    }
else
    log_warn "Validation script not found, skipping validation"
fi

# Parse DATABASE_URL to extract components
if [ -n "$DATABASE_URL" ]; then
    log_info "DATABASE_URL is set"
    log_info "Waiting for PostgreSQL..."
    
    # For docker-compose, the host is simply 'postgres' as defined in the service name
    # The DATABASE_URL from docker-compose.yml is: postgresql://kamailio:kamailiopw@postgres/kamailio
    DB_HOST="${DB_HOST:-postgres}"
    DB_PORT="${DB_PORT:-5432}"
    
    echo "Checking connection to $DB_HOST:$DB_PORT"
    
    # Wait for DNS to resolve
    echo "Waiting for DNS resolution..."
    for i in {1..30}; do
        if nslookup $DB_HOST 2>/dev/null | grep -q "Address"; then
            echo "DNS resolved for $DB_HOST"
            break
        fi
        echo "Waiting for DNS... attempt $i/30"
        sleep 2
    done
    
    # Wait for PostgreSQL to be ready
    while ! nc -zv $DB_HOST $DB_PORT 2>&1 | grep -q succeeded; do
        echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
        sleep 2
    done
    
    echo "PostgreSQL is ready!"
    
    # Additional check with pg_isready
    while ! pg_isready -h $DB_HOST -p $DB_PORT -U kamailio; do
        echo "Waiting for PostgreSQL to accept connections..."
        sleep 2
    done
    
    echo "PostgreSQL is accepting connections!"
    
    # Give PostgreSQL a moment to fully initialize
    sleep 2
fi

# Initialize database
echo "Initializing database..."
python3 /app/scripts/init-database.py

# Create log directories
echo "Creating log directories..."
mkdir -p /var/log/kamailio
mkdir -p /var/log

# Test services individually first (non-fatal)
echo "Testing SIP integration modules..."
cd /app
python3 -c "
import sys
sys.path.insert(0, '/app')
try:
    from src.api.sip_integration import app
    print('✅ SIP API integration imports successfully')
except Exception as e:
    print(f'❌ SIP API integration import failed: {e}')
    import traceback
    traceback.print_exc()
" || echo "Warning: SIP API integration test failed (non-fatal)"

echo "Testing call manager..."
python3 -c "
import sys
sys.path.insert(0, '/app')
try:
    from src.call_handling.call_manager import CallManager
    print('✅ Call manager imports successfully')
except Exception as e:
    print(f'❌ Call manager import failed: {e}')
    import traceback
    traceback.print_exc()
" || echo "Warning: Call manager test failed (non-fatal)"

echo "Testing WebSocket integration..."
python3 -c "
import sys
sys.path.insert(0, '/app')
try:
    from src.call_handling.websocket_integration import WebSocketCallBridge
    print('✅ WebSocket integration imports successfully')
except Exception as e:
    print(f'❌ WebSocket integration import failed: {e}')
    import traceback
    traceback.print_exc()
" || echo "Warning: WebSocket integration test failed (non-fatal)"

echo "Testing main integration..."
python3 -c "
import sys
sys.path.insert(0, '/app')
try:
    from src.main_integration import SIPIntegrationServer
    print('✅ Main integration imports successfully')
except Exception as e:
    print(f'❌ Main integration import failed: {e}')
    import traceback
    traceback.print_exc()
" || echo "Warning: Main integration test failed (non-fatal)"

echo "Testing Kamailio config..."
kamailio -c -f /etc/kamailio/kamailio.cfg
if [ $? -eq 0 ]; then
    echo "✅ Kamailio config is valid"
else
    echo "❌ Kamailio config has errors"
fi

# Start all services with supervisor (including RTP bridge)
echo "Starting all services..."
# Check for supervisord in different locations
if [ -x "/usr/bin/supervisord" ]; then
    exec /usr/bin/supervisord -c /etc/supervisord.conf
elif [ -x "/usr/local/bin/supervisord" ]; then
    exec /usr/local/bin/supervisord -c /etc/supervisord.conf
elif command -v supervisord &> /dev/null; then
    exec supervisord -c /etc/supervisord.conf
else
    echo "ERROR: supervisord not found!"
    exit 1
fi
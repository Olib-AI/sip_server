#!/bin/bash
set -ex  # Add -x for debug output

# Add error handling
trap 'echo "Error on line $LINENO" >&2' ERR

# Parse DATABASE_URL to extract components
if [ -n "$DATABASE_URL" ]; then
    echo "DATABASE_URL: $DATABASE_URL"
    echo "Waiting for PostgreSQL..."
    
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
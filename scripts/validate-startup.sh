#!/bin/bash
# Startup validation script to catch common issues early

set -e

echo "=== SIP Server Startup Validation ==="
echo "Time: $(date)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Error counter
ERRORS=0
WARNINGS=0

# Function to report errors
error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
    ((ERRORS++))
}

# Function to report warnings
warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}" >&2
    ((WARNINGS++))
}

# Function to report success
success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

# Check if running in Docker
if [ -f /.dockerenv ]; then
    success "Running in Docker container"
else
    warning "Not running in Docker container"
fi

# 1. Check required environment variables
echo -e "\n=== Checking Environment Variables ==="
REQUIRED_VARS=(
    "DATABASE_URL"
    "DB_HOST"
    "DB_PORT"
    "DB_NAME"
    "DB_USER"
    "DB_PASSWORD"
    "API_PORT"
    "WEBSOCKET_PORT"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        error "Missing required environment variable: $var"
    else
        success "$var is set"
    fi
done

# 2. Check optional but important variables
OPTIONAL_VARS=(
    "AI_PLATFORM_WS_URL"
    "SIP_DOMAIN"
    "LOG_LEVEL"
)

for var in "${OPTIONAL_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        warning "Optional variable not set: $var (using defaults)"
    else
        success "$var is set"
    fi
done

# 3. Validate DATABASE_URL format
echo -e "\n=== Validating Database Configuration ==="
if [ -n "$DATABASE_URL" ]; then
    if [[ "$DATABASE_URL" =~ ^postgresql://.*@.*/.* ]]; then
        success "DATABASE_URL format looks valid"
    else
        error "DATABASE_URL format is invalid. Expected: postgresql://user:pass@host:port/dbname"
    fi
fi

# 4. Check Python installation
echo -e "\n=== Checking Python Environment ==="
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    success "Python installed: $PYTHON_VERSION"
else
    error "Python3 is not installed"
fi

# 5. Check required Python modules
echo -e "\n=== Checking Python Dependencies ==="
python3 -c "
import sys
sys.path.insert(0, '/app')
missing_modules = []
required_modules = [
    'fastapi',
    'uvicorn',
    'websockets',
    'asyncpg',
    'pydantic',
    'aiofiles'
]

for module in required_modules:
    try:
        __import__(module)
        print(f'✓ {module}')
    except ImportError:
        missing_modules.append(module)
        print(f'✗ {module}')

if missing_modules:
    print(f'\\nERROR: Missing Python modules: {missing_modules}')
    sys.exit(1)
" || error "Python dependency check failed"

# 6. Check Kamailio installation
echo -e "\n=== Checking Kamailio ==="
if command -v kamailio &> /dev/null; then
    KAMAILIO_VERSION=$(kamailio -v 2>&1 | head -n1)
    success "Kamailio installed: $KAMAILIO_VERSION"
else
    error "Kamailio is not installed"
fi

# 7. Check supervisord
echo -e "\n=== Checking Supervisor ==="
if command -v supervisord &> /dev/null; then
    success "Supervisord found at: $(which supervisord)"
elif [ -x "/usr/bin/supervisord" ]; then
    success "Supervisord found at: /usr/bin/supervisord"
elif [ -x "/usr/local/bin/supervisord" ]; then
    success "Supervisord found at: /usr/local/bin/supervisord"
else
    error "Supervisord not found in any expected location"
fi

# 8. Check configuration files
echo -e "\n=== Checking Configuration Files ==="
CONFIG_FILES=(
    "/etc/kamailio/kamailio.cfg"
    "/etc/supervisord.conf"
    "/app/scripts/startup.sh"
)

for file in "${CONFIG_FILES[@]}"; do
    if [ -f "$file" ]; then
        success "Found: $file"
    else
        error "Missing: $file"
    fi
done

# 9. Check network connectivity (if in Docker)
echo -e "\n=== Checking Network ==="
if [ -n "$DB_HOST" ] && [ "$DB_HOST" != "localhost" ] && [ "$DB_HOST" != "127.0.0.1" ]; then
    if command -v nslookup &> /dev/null; then
        if nslookup "$DB_HOST" &> /dev/null; then
            success "DNS resolution works for DB_HOST: $DB_HOST"
        else
            error "Cannot resolve DB_HOST: $DB_HOST"
        fi
    else
        warning "nslookup not available, skipping DNS check"
    fi
fi

# 10. Check port availability
echo -e "\n=== Checking Port Availability ==="
check_port() {
    local port=$1
    local name=$2
    if command -v netstat &> /dev/null; then
        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            warning "Port $port ($name) is already in use"
        else
            success "Port $port ($name) is available"
        fi
    else
        warning "netstat not available, cannot check port $port"
    fi
}

check_port "${API_PORT:-8080}" "API"
check_port "${WEBSOCKET_PORT:-8081}" "WebSocket"
check_port "${SIP_PORT:-5060}" "SIP"

# Summary
echo -e "\n=== Validation Summary ==="
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}Found $ERRORS errors that must be fixed before starting.${NC}"
    echo -e "${RED}The container will likely fail to start properly.${NC}"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}Found $WARNINGS warnings. The container may start but with limited functionality.${NC}"
    exit 0
else
    echo -e "${GREEN}All checks passed! Container should start successfully.${NC}"
    exit 0
fi
#!/bin/bash
# Docker environment validation script
# Run this BEFORE starting docker-compose to catch issues early

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
    ((ERRORS++))
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}" >&2
}

success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

echo "=== Docker Environment Validation ==="
echo "Time: $(date)"

# 1. Check Docker is running
echo -e "\n=== Checking Docker ==="
if docker info &>/dev/null; then
    success "Docker daemon is running"
else
    error "Docker daemon is not running. Please start Docker Desktop."
    exit 1
fi

# 2. Check docker-compose
if command -v docker-compose &>/dev/null || docker compose version &>/dev/null; then
    success "docker-compose is available"
else
    error "docker-compose is not installed"
fi

# 3. Check .env file
echo -e "\n=== Checking Environment Files ==="
if [ -f .env ]; then
    success "Found .env file"
    
    # Check for common missing variables
    source .env
    if [ -z "$DATABASE_URL" ]; then
        error ".env is missing DATABASE_URL variable"
        echo "  Add: DATABASE_URL=postgresql://kamailio:kamailiopw@postgres:5432/kamailio"
    fi
else
    error "Missing .env file. Copy example.env to .env and configure it."
    echo "  Run: cp example.env .env"
fi

# 4. Check required files exist
echo -e "\n=== Checking Required Files ==="
REQUIRED_FILES=(
    "docker-compose.yml"
    "Dockerfile"
    "requirements.txt"
    "scripts/startup.sh"
    "config/kamailio.cfg"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        success "Found: $file"
    else
        error "Missing: $file"
    fi
done

# 5. Check port conflicts
echo -e "\n=== Checking Port Availability ==="
check_port() {
    local port=$1
    local service=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        error "Port $port ($service) is already in use"
        echo "  Run: lsof -i :$port to see what's using it"
    else
        success "Port $port ($service) is available"
    fi
}

check_port 5432 "PostgreSQL"
check_port 8080 "API Server"
check_port 8081 "WebSocket Bridge"
check_port 5060 "SIP"

# 6. Check Docker resources
echo -e "\n=== Checking Docker Resources ==="
DOCKER_MEM=$(docker system info --format '{{.MemTotal}}' 2>/dev/null || echo "0")
if [ "$DOCKER_MEM" != "0" ]; then
    MEM_GB=$((DOCKER_MEM / 1073741824))
    if [ $MEM_GB -lt 2 ]; then
        warning "Docker has less than 2GB memory allocated ($MEM_GB GB)"
        echo "  Increase Docker Desktop memory allocation for better performance"
    else
        success "Docker has $MEM_GB GB memory allocated"
    fi
fi

# 7. Check for common Docker issues
echo -e "\n=== Checking Common Issues ==="

# Check for problematic EXPOSE ranges
if grep -q "EXPOSE.*10000-20000" Dockerfile; then
    warning "Large port range in EXPOSE directive can cause issues"
    echo "  Consider removing or reducing the RTP port range"
fi

# Check for orphan containers
ORPHANS=$(docker ps -a --filter "name=sip_server" --format "{{.Names}}" | wc -l)
if [ $ORPHANS -gt 0 ]; then
    warning "Found $ORPHANS existing sip_server containers"
    echo "  Run: docker-compose down -v to clean up"
fi

# Summary
echo -e "\n=== Validation Summary ==="
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}Found $ERRORS critical errors. Fix these before running docker-compose.${NC}"
    echo -e "\n${YELLOW}Common fixes:${NC}"
    echo "1. Ensure Docker Desktop is running"
    echo "2. Copy example.env to .env: cp example.env .env"
    echo "3. Stop conflicting services using the ports"
    echo "4. Run: docker-compose down -v to clean up"
    exit 1
else
    echo -e "${GREEN}All checks passed! You can run: docker-compose up${NC}"
fi
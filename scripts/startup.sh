#!/bin/bash
set -e

# Parse DATABASE_URL to extract components
if [ -n "$DATABASE_URL" ]; then
    echo "DATABASE_URL: $DATABASE_URL"
    echo "Waiting for PostgreSQL..."
    
    # For docker-compose, the host is simply 'postgres' as defined in the service name
    # The DATABASE_URL from docker-compose.yml is: postgresql://kamailio:kamailiopw@postgres/kamailio
    DB_HOST="postgres"
    DB_PORT="5432"
    
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

# Start supervisord
echo "Starting services..."
exec /usr/bin/supervisord -c /etc/supervisord.conf
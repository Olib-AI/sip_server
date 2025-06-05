# Multi-stage Dockerfile for Olib AI SIP Server

# Stage 1: Build RTPEngine
FROM alpine:3.18 AS rtpengine-builder

RUN apk add --no-cache \
    build-base \
    git \
    libevent-dev \
    pcre-dev \
    xmlrpc-c-dev \
    hiredis-dev \
    openssl-dev \
    glib-dev \
    zlib-dev \
    mariadb-dev \
    curl-dev \
    libnfnetlink-dev \
    libnetfilter_conntrack-dev \
    iptables-dev \
    libpcap-dev \
    json-glib-dev \
    libwebsockets-dev

WORKDIR /build
RUN git clone https://github.com/sipwise/rtpengine.git && \
    cd rtpengine && \
    make

# Stage 2: Final image
FROM alpine:3.18

# Install runtime dependencies
RUN apk add --no-cache \
    kamailio \
    kamailio-db \
    kamailio-json \
    kamailio-websocket \
    kamailio-tls \
    kamailio-http-async \
    kamailio-jansson \
    kamailio-rtpengine \
    kamailio-presence \
    kamailio-postgres \
    python3 \
    py3-pip \
    postgresql-client \
    supervisor \
    iptables \
    libevent \
    pcre \
    xmlrpc-c \
    hiredis \
    openssl \
    glib \
    json-glib \
    libwebsockets \
    curl \
    bash

# Copy RTPEngine from builder
COPY --from=rtpengine-builder /build/rtpengine/daemon/rtpengine /usr/local/bin/
COPY --from=rtpengine-builder /build/rtpengine/iptables-extension/*.so /usr/lib/xtables/

# Create directories
RUN mkdir -p /etc/kamailio \
    /var/run/kamailio \
    /var/log/kamailio \
    /var/run/rtpengine \
    /app \
    /app/config \
    /app/scripts

# Set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Copy Kamailio configuration
COPY config/kamailio.cfg /etc/kamailio/kamailio.cfg

# Create RTPEngine configuration
RUN mkdir -p /etc/rtpengine && \
    echo '[rtpengine]' > /etc/rtpengine/rtpengine.conf && \
    echo 'interface = 0.0.0.0' >> /etc/rtpengine/rtpengine.conf && \
    echo 'listen-ng = 127.0.0.1:2223' >> /etc/rtpengine/rtpengine.conf && \
    echo 'port-min = 10000' >> /etc/rtpengine/rtpengine.conf && \
    echo 'port-max = 20000' >> /etc/rtpengine/rtpengine.conf && \
    echo 'log-level = 6' >> /etc/rtpengine/rtpengine.conf && \
    echo 'log-facility = daemon' >> /etc/rtpengine/rtpengine.conf

# Create supervisor configuration
RUN echo '[supervisord]' > /etc/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisord.conf && \
    echo 'user=root' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:kamailio]' >> /etc/supervisord.conf && \
    echo 'command=/usr/sbin/kamailio -DD -E -e -m 256 -M 32' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/var/log/kamailio/kamailio.log' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/var/log/kamailio/kamailio_error.log' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:rtpengine]' >> /etc/supervisord.conf && \
    echo 'command=/usr/local/bin/rtpengine --config-file=/etc/rtpengine/rtpengine.conf' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/var/log/rtpengine.log' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/var/log/rtpengine_error.log' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:websocket-bridge]' >> /etc/supervisord.conf && \
    echo 'command=python3 -m src.websocket.bridge' >> /etc/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/var/log/websocket-bridge.log' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/var/log/websocket-bridge_error.log' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:api-server]' >> /etc/supervisord.conf && \
    echo 'command=python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000' >> /etc/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/var/log/api-server.log' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/var/log/api-server_error.log' >> /etc/supervisord.conf

# Create startup script
RUN echo '#!/bin/bash' > /app/scripts/startup.sh && \
    echo 'set -e' >> /app/scripts/startup.sh && \
    echo '' >> /app/scripts/startup.sh && \
    echo '# Wait for PostgreSQL if needed' >> /app/scripts/startup.sh && \
    echo 'if [ -n "$DATABASE_URL" ]; then' >> /app/scripts/startup.sh && \
    echo '    echo "Waiting for PostgreSQL..."' >> /app/scripts/startup.sh && \
    echo '    while ! pg_isready -d $DATABASE_URL; do' >> /app/scripts/startup.sh && \
    echo '        sleep 1' >> /app/scripts/startup.sh && \
    echo '    done' >> /app/scripts/startup.sh && \
    echo '    echo "PostgreSQL is ready"' >> /app/scripts/startup.sh && \
    echo 'fi' >> /app/scripts/startup.sh && \
    echo '' >> /app/scripts/startup.sh && \
    echo '# Initialize database' >> /app/scripts/startup.sh && \
    echo 'python3 -c "from src.models.database import init_db; import asyncio; asyncio.run(init_db())"' >> /app/scripts/startup.sh && \
    echo '' >> /app/scripts/startup.sh && \
    echo '# Start supervisord' >> /app/scripts/startup.sh && \
    echo 'exec /usr/bin/supervisord -c /etc/supervisord.conf' >> /app/scripts/startup.sh && \
    chmod +x /app/scripts/startup.sh

# Expose ports
EXPOSE 5060/udp 5060/tcp 5061/tcp 8000 8080 10000-20000/udp

# Environment variables
ENV PYTHONPATH=/app \
    KAMAILIO_SHARED_MEMORY=256 \
    KAMAILIO_PKG_MEMORY=32 \
    DATABASE_URL=postgresql://kamailio:kamailiopw@postgres/kamailio \
    JWT_SECRET_KEY=change-this-secret-key-in-production \
    AI_PLATFORM_URL=ws://ai-platform:8001/ws/voice

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run startup script
CMD ["/app/scripts/startup.sh"]
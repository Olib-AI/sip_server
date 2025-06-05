# Dockerfile for Olib AI SIP Server
FROM alpine:3.22

# Install runtime dependencies
RUN apk add --no-cache \
    kamailio \
    kamailio-db \
    kamailio-json \
    kamailio-websocket \
    kamailio-tls \
    kamailio-jansson \
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
    bash \
    netcat-openbsd \
    bind-tools

# Note: RTPEngine will be handled by Kamailio's rtpproxy module or external service

# Create directories
RUN mkdir -p /etc/kamailio \
    /var/run/kamailio \
    /var/log/kamailio \
    /app \
    /app/config \
    /app/scripts

# Set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Copy Kamailio configuration
COPY config/kamailio.cfg /etc/kamailio/kamailio.cfg

# RTP port range will be handled by Kamailio directly

# Create supervisor configuration
RUN echo '[supervisord]' > /etc/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisord.conf && \
    echo 'user=root' >> /etc/supervisord.conf && \
    echo 'loglevel=info' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:kamailio]' >> /etc/supervisord.conf && \
    echo 'command=/usr/sbin/kamailio -DD -E -e -m 256 -M 32' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:websocket-bridge]' >> /etc/supervisord.conf && \
    echo 'command=python3 src/websocket/bridge.py' >> /etc/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'environment=PYTHONPATH="/app"' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:api-server]' >> /etc/supervisord.conf && \
    echo 'command=python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000' >> /etc/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'environment=PYTHONPATH="/app"' >> /etc/supervisord.conf

# Make startup script executable
RUN chmod +x /app/scripts/startup.sh

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
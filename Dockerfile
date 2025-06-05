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
    kamailio-postgres \
    kamailio-extras \
    kamailio-utils \
    kamailio-http_async \
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
    bind-tools \
    git \
    autoconf \
    automake \
    libtool

# Note: RTPEngine will be handled by Kamailio's rtpproxy module or external service

# Create directories
RUN mkdir -p /etc/kamailio \
    /var/run/kamailio \
    /var/log/kamailio \
    /var/run/rtpproxy \
    /tmp/rtpproxy \
    /app \
    /app/config \
    /app/scripts

# Set working directory
WORKDIR /app

# Install build dependencies for Python packages and RTPproxy
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    linux-headers \
    g++ \
    make \
    python3-dev

# Note: We'll use our custom RTP-WebSocket bridge instead of external RTPproxy

# Copy Python requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Remove build dependencies to reduce image size
RUN apk del .build-deps

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Copy Kamailio configuration
COPY config/kamailio.cfg /etc/kamailio/kamailio.cfg

# Copy RTPproxy configuration
COPY config/rtpproxy.conf /etc/rtpproxy.conf

# RTP port range will be handled by Kamailio directly

# Create supervisor configuration
RUN echo '[supervisord]' > /etc/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisord.conf && \
    echo 'user=root' >> /etc/supervisord.conf && \
    echo 'loglevel=info' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:kamailio]' >> /etc/supervisord.conf && \
    echo 'command=/usr/sbin/kamailio -DD -E -e -m 256 -M 32 -f /etc/kamailio/kamailio.cfg' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'priority=200' >> /etc/supervisord.conf && \
    echo 'startsecs=5' >> /etc/supervisord.conf && \
    echo '' >> /etc/supervisord.conf && \
    echo '[program:sip-integration]' >> /etc/supervisord.conf && \
    echo 'command=python3 -m src.main_integration' >> /etc/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisord.conf && \
    echo 'environment=PYTHONPATH="/app"' >> /etc/supervisord.conf && \
    echo 'priority=100' >> /etc/supervisord.conf

# Make startup scripts executable
RUN chmod +x /app/scripts/startup.sh && \
    chmod +x /app/scripts/startup-debug.sh || true

# Expose ports
EXPOSE 5060/udp 5060/tcp 5061/tcp 8000 8080 8081

# Environment variables (defaults - use .env file to override)
ENV PYTHONPATH=/app

# Health check with better error reporting
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD /app/scripts/health-check.sh || exit 1

# Run startup script
CMD ["/bin/bash", "/app/scripts/startup.sh"]
# Olib AI SIP Server Makefile

.PHONY: help build test lint format clean dev-up dev-down logs shell

# Default target
help:
	@echo "Available commands:"
	@echo "  build      - Build Docker image"
	@echo "  test       - Run tests"
	@echo "  lint       - Run linting"
	@echo "  format     - Format code"
	@echo "  clean      - Clean up containers and images"
	@echo "  dev-up     - Start development environment"
	@echo "  dev-down   - Stop development environment"
	@echo "  logs       - Show logs"
	@echo "  shell      - Access container shell"
	@echo "  load-test  - Run load tests"

# Variables
IMAGE_NAME ?= olib-sip-server
IMAGE_TAG ?= latest
DOCKER_COMPOSE = docker-compose
PYTEST_ARGS ?= --verbose

# Build Docker image
build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

# Run tests
test:
	$(DOCKER_COMPOSE) exec sip-server pytest $(PYTEST_ARGS)

# Run tests with coverage
test-coverage:
	$(DOCKER_COMPOSE) exec sip-server pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific test file
test-file:
	$(DOCKER_COMPOSE) exec sip-server pytest src/tests/$(FILE)

# Run linting
lint:
	$(DOCKER_COMPOSE) exec sip-server pylint src/
	$(DOCKER_COMPOSE) exec sip-server mypy src/

# Format code
format:
	$(DOCKER_COMPOSE) exec sip-server black src/
	$(DOCKER_COMPOSE) exec sip-server black --check src/

# Start development environment
dev-up:
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Services are ready!"
	@echo "API: http://localhost:8000"
	@echo "WebSocket: ws://localhost:8080"
	@echo "Grafana: http://localhost:3000 (admin/admin)"

# Stop development environment
dev-down:
	$(DOCKER_COMPOSE) down

# Show logs
logs:
	$(DOCKER_COMPOSE) logs -f

# Show logs for specific service
logs-service:
	$(DOCKER_COMPOSE) logs -f $(SERVICE)

# Access container shell
shell:
	$(DOCKER_COMPOSE) exec sip-server /bin/bash

# Access database shell
db-shell:
	$(DOCKER_COMPOSE) exec postgres psql -U kamailio -d kamailio

# Run load tests
load-test:
	python src/tests/load_test.py --url http://localhost:8000

# Run specific load test
load-test-endpoint:
	python src/tests/load_test.py --url http://localhost:8000 --test $(TEST) --requests $(REQUESTS)

# Clean up containers and images
clean:
	$(DOCKER_COMPOSE) down -v
	docker system prune -f
	docker volume prune -f

# Clean and rebuild
rebuild: clean build dev-up

# Check health
health:
	curl -f http://localhost:8000/health

# Get server status
status:
	curl -s http://localhost:8000/api/config/status | jq .

# View active calls
calls:
	curl -s http://localhost:8000/api/calls/active | jq .

# Initialize database
init-db:
	$(DOCKER_COMPOSE) exec sip-server python -c "from src.models.database import init_db; import asyncio; asyncio.run(init_db())"

# Backup database
backup-db:
	$(DOCKER_COMPOSE) exec postgres pg_dump -U kamailio kamailio > backup_$(shell date +%Y%m%d_%H%M%S).sql

# Restore database
restore-db:
	$(DOCKER_COMPOSE) exec -T postgres psql -U kamailio kamailio < $(BACKUP_FILE)

# View Kamailio stats
kamailio-stats:
	$(DOCKER_COMPOSE) exec sip-server kamctl stats

# Reload Kamailio config
kamailio-reload:
	$(DOCKER_COMPOSE) exec sip-server kamctl reload

# Monitor SIP traffic
monitor-sip:
	$(DOCKER_COMPOSE) exec sip-server tcpdump -i any -n port 5060

# Tail application logs
tail-logs:
	$(DOCKER_COMPOSE) exec sip-server tail -f /var/log/api-server.log

# Check disk usage
disk-usage:
	$(DOCKER_COMPOSE) exec sip-server df -h

# Check memory usage
memory-usage:
	$(DOCKER_COMPOSE) exec sip-server free -h

# Production build (multi-platform)
build-prod:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG) --push .

# Security scan
security-scan:
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
		-v $(HOME)/Library/Caches:/root/.cache/ \
		aquasec/trivy image $(IMAGE_NAME):$(IMAGE_TAG)

# Generate API documentation
docs:
	$(DOCKER_COMPOSE) exec sip-server python -c "import json; from src.api.main import app; print(json.dumps(app.openapi(), indent=2))" > api_docs.json

# Validate configuration
validate-config:
	$(DOCKER_COMPOSE) exec sip-server kamailio -c -f /etc/kamailio/kamailio.cfg

# Performance test
perf-test:
	$(DOCKER_COMPOSE) exec sip-server python src/tests/load_test.py --test all --requests 1000

# Install development dependencies
install-dev:
	pip install -r requirements.txt
	pip install pytest-asyncio pytest-cov black pylint mypy

# Run pre-commit checks
pre-commit: format lint test

# Setup development environment
setup: build dev-up init-db
	@echo "Development environment is ready!"
	@echo "Run 'make test' to run tests"
	@echo "Run 'make health' to check API health"
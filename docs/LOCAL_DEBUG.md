# Local Development & Debugging Guide

## Production-Ready Development Environment ✅

### 1. Environment Setup (Validated Configuration)
```bash
# Copy example environment file
cp example.env .env

# Edit configuration for your environment (all variables validated)
vim .env

# Validate configuration
python src/utils/config.py  # Validates all config parameters
```

### 2. Development Workflow (Validated & Tested)
```bash
# Start complete development environment (all services)
docker-compose up -d

# View real-time logs for all services
docker-compose logs -f

# View specific service logs
docker-compose logs -f sip-server
docker-compose logs -f postgres
docker-compose logs -f rtpproxy

# Check service status (all should be healthy)
docker-compose ps

# Make code changes, then restart
docker-compose restart sip-server

# For major changes, rebuild with validation
docker-compose down
docker-compose build sip-server
docker-compose up -d

# Validate everything is working
python src/tests/run_tests.py  # Should show 159 tests passing
```

### 3. Comprehensive Test Environment (159 Tests Passing)
```bash
# Run complete validated test suite
python src/tests/run_tests.py

# Run specific test categories
python -m pytest src/tests/unit/ -v          # Unit tests (95+ components)
python -m pytest src/tests/integration/ -v   # Integration tests (API + WebSocket)
python -m pytest src/tests/e2e/ -v          # End-to-end tests

# Run AI integration validation
python src/tests/validate_ai_integration_realistic.py

# Performance and load testing
python -m pytest src/tests/load/ -v
python -m pytest src/tests/performance/ -v
```

## Debugging Process (Production-Ready Methodology)

### Systematic Debugging Approach
1. **Service Health Check**: `docker-compose ps` (all should show "Up")
2. **Log Analysis**: `docker-compose logs -f sip-server` (structured logging)
3. **Component Validation**: Test individual components with validated tests
4. **Integration Verification**: Run `python src/tests/validate_ai_integration_realistic.py`
5. **Performance Check**: Validate response times and resource usage
6. **Fix & Validate**: Apply fixes and run test suite (159 tests should pass)

### Issue Priority Guidelines (Production Focus)

**CRITICAL PRIORITY** (Fix immediately - Production Impact):
- Service startup failures or crashes
- Database connection loss
- WebSocket bridge disconnection from AI platform
- Authentication failures (JWT/HMAC)
- Audio processing pipeline failures
- Security vulnerabilities or exposed secrets

**HIGH PRIORITY** (Fix within hours - Quality Impact):
- Performance degradation (>600ms latency)
- Memory leaks or resource exhaustion
- Call state synchronization issues
- DTMF detection failures
- SMS delivery problems

**MEDIUM PRIORITY** (Fix within days - Enhancement):
- Non-critical module warnings
- Configuration optimizations
- Test coverage improvements
- Documentation updates

**LOW PRIORITY** (Fix during maintenance):
- Code style improvements
- Non-functional optimizations
- Development convenience features

## Development Rules

**IMPORTANT**: When fixing issues, ensure changes don't break existing functionality.

### Before Making Changes
- Review existing code structure and dependencies thoroughly
- Identify potential side effects on other components
- Verify all edge cases are handled
- Check for race conditions in concurrent operations
- Ensure backward compatibility where needed

### For Each Change
- Provide complete implementations, not partial updates
- Include necessary imports and dependencies
- Handle all error cases and exceptions
- Include proper null checks and input validation
- Maintain current method signatures where possible
- Preserve existing behavior for dependent code

### Validation Requirements
- Verify solution meets all functional requirements
- Confirm it follows existing patterns and conventions
- Check performance implications
- Ensure thread safety if applicable
- Verify changes don't break existing interfaces

### Code Quality Standards
- Don't assume anything - verify all assumptions
- Provide production-ready code rather than examples
- Include complete methods/classes with proper context
- Focus on working, tested solutions

## Common Issues & Solutions

### RTPproxy Connection Failures
- Ensure RTP bridge starts before Kamailio
- Check port 12221 availability
- Verify RTPproxy protocol compliance

### Database Issues
- Confirm PostgreSQL service is ready
- Check table existence and permissions
- Validate connection strings

### Module Loading Errors
- Verify all required Kamailio modules are installed
- Check module dependencies
- Review configuration syntax

## Testing Commands

### Health Checks (Production Validated)
```bash
# Check all services status (all should show "Up")
docker-compose ps

# API health endpoint (should return 200 OK)
curl http://localhost:8080/health

# Check Prometheus metrics (should return metrics data)
curl http://localhost:8080/metrics

# WebSocket connectivity test (with proper auth)
curl -H "Authorization: Bearer your_jwt_token" \
     -H "Upgrade: websocket" \
     -H "Connection: Upgrade" \
     http://localhost:8080/ws/

# Database connection validation
docker-compose exec sip-server python3 -c "
from src.utils.config import get_config
from src.models.database import get_database_url
print('✅ Config loaded:', get_config().database.host)
print('✅ Database URL working')
"

# Audio resampler validation
docker-compose exec sip-server python3 -c "
from src.audio.resampler import AudioResampler
import numpy as np
resampler = AudioResampler()
test_audio = np.random.randint(-32768, 32767, 160, dtype=np.int16).tobytes()
result = resampler.resample_audio(test_audio, 8000, 16000)
print(f'✅ Audio resampling: {len(test_audio)} -> {len(result)} bytes')
"
```

### API Testing (All Endpoints Validated)
```bash
# Test configuration endpoint
curl http://localhost:8080/api/config/status

# Test health monitoring
curl http://localhost:8080/api/config/health

# Test call management (with authentication)
curl -X POST http://localhost:8080/api/calls/initiate \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer your_jwt_token" \
     -d '{
       "from_number": "+1234567890", 
       "to_number": "+0987654321",
       "webhook_url": "https://your-app.com/webhook"
     }'

# Test SMS functionality
curl -X POST http://localhost:8080/api/sms/send \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer your_jwt_token" \
     -d '{
       "from_number": "+1234567890", 
       "to_number": "+0987654321", 
       "message": "Test message from SIP server"
     }'

# Get active calls with statistics
curl -H "Authorization: Bearer your_jwt_token" \
     http://localhost:8080/api/calls/active

# Test trunk management
curl -H "Authorization: Bearer your_jwt_token" \
     http://localhost:8080/api/trunks

# Test number blocking functionality
curl -X POST http://localhost:8080/api/numbers/block \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer your_jwt_token" \
     -d '{"number": "+1234567890", "reason": "Test block"}'
```

### Comprehensive Test Suite (159 Tests Validated)
```bash
# Run complete validated test suite (should show 159 passing, 0 failures)
python src/tests/run_tests.py

# Run tests with detailed output
python -m pytest src/tests/ -v --tb=short

# Run specific validated test categories
python -m pytest src/tests/unit/ -v                    # Unit tests (95+ components)
python -m pytest src/tests/integration/ -v            # Integration tests
python -m pytest src/tests/e2e/ -v                    # End-to-end scenarios

# Run AI integration validation (should show 14+ successes)
python src/tests/validate_ai_integration_realistic.py

# Run tests with coverage reporting
python -m pytest src/tests/ --cov=src --cov-report=html --cov-report=term

# Performance testing
python -m pytest src/tests/performance/ -v
python -m pytest src/tests/load/ -v

# Configuration validation
python3 -c "
from src.utils.config import get_config
config = get_config()
print('✅ Configuration loaded successfully')
print(f'✅ Database: {config.database.host}:{config.database.port}')
print(f'✅ SIP Domain: {config.sip.domain}')
print(f'✅ WebSocket Port: {config.websocket.port}')
print(f'✅ AI Platform URL: {config.ai_platform.websocket_url}')
"
```

### Component Testing (Production Validated)
```bash
# Test Call Manager (comprehensive validation)
python3 -c "
from src.call_handling.call_manager import CallManager
from unittest.mock import AsyncMock
manager = CallManager(max_concurrent_calls=20, ai_websocket_manager=AsyncMock())
print('✅ CallManager initialized successfully')
print(f'✅ Max concurrent calls: {manager.max_concurrent_calls}')
"

# Test WebSocket Bridge (with realistic config)
python3 -c "
from src.websocket.bridge import WebSocketBridge
from src.utils.config import get_config
config = get_config()
bridge = WebSocketBridge(config.ai_platform.websocket_url)
print('✅ WebSocketBridge initialized successfully')
print(f'✅ AI Platform URL: {bridge.ai_platform_url}')
"

# Test Audio Processing Pipeline (8kHz ↔ 16kHz validated)
python3 -c "
from src.audio.codecs import AudioProcessor
from src.audio.resampler import AudioResampler
import numpy as np

# Test codec conversion
processor = AudioProcessor()
test_pcmu = b'\\x00\\xFF' * 80  # Sample PCMU data
pcm_data = processor.convert_format(test_pcmu, 'PCMU', 'PCM')
print(f'✅ Codec conversion: PCMU ({len(test_pcmu)}) -> PCM ({len(pcm_data)})')

# Test resampling (critical for AI integration)
resampler = AudioResampler()
audio_8k = np.random.randint(-32768, 32767, 160, dtype=np.int16).tobytes()
audio_16k = resampler.resample_audio(audio_8k, 8000, 16000)
print(f'✅ Resampling: 8kHz ({len(audio_8k)}) -> 16kHz ({len(audio_16k)})')
"

# Test SMS System (complete implementation)
python3 -c "
from src.sms.sms_manager import SMSManager
from src.sms.sms_queue import SMSQueue
from unittest.mock import AsyncMock

queue = SMSQueue(max_size=1000)
manager = SMSManager(sms_queue=queue, sip_integration=AsyncMock())
print('✅ SMS System initialized successfully')
print(f'✅ Queue capacity: {queue.max_size}')
"

# Test DTMF System (complete with IVR)
python3 -c "
from src.dtmf.dtmf_detector import DTMFDetector
from src.dtmf.dtmf_processor import DTMFProcessor
from src.dtmf.ivr_manager import IVRManager
from unittest.mock import AsyncMock

detector = DTMFDetector()
processor = DTMFProcessor(ai_integration=AsyncMock())
ivr = IVRManager()
print('✅ DTMF System initialized successfully')
print('✅ Supports RFC 2833 and in-band detection')
print('✅ IVR menu system ready')
"
```

### Kamailio Testing
```bash
# Test Kamailio configuration
docker-compose exec sip-server kamailio -c -f /etc/kamailio/kamailio.cfg

# Check Kamailio process
docker-compose exec sip-server pgrep kamailio

# Monitor SIP traffic (if needed)
docker-compose exec sip-server tcpdump -i any port 5060 -n
```

## Emergency Recovery (Production-Ready Procedures)

### Quick Recovery (System Becomes Unstable)
```bash
# 1. Full system reset with validation
docker-compose down -v
docker-compose build --no-cache sip-server
docker-compose up -d

# 2. Validate all services are healthy
docker-compose ps
# All services should show "Up" status

# 3. Run quick health checks
curl http://localhost:8080/health  # Should return 200 OK
python src/tests/run_tests.py     # Should show 159 tests passing

# 4. Review logs for any remaining issues
docker-compose logs -f
```

### Production Recovery Checklist

**Immediate Actions:**
1. ✅ Stop all services: `docker-compose down`
2. ✅ Clear volumes if needed: `docker-compose down -v`
3. ✅ Rebuild containers: `docker-compose build --no-cache`
4. ✅ Start services: `docker-compose up -d`

**Validation Steps:**
1. ✅ Service health: `docker-compose ps` (all "Up")
2. ✅ API health: `curl http://localhost:8080/health`
3. ✅ Database connectivity: Test config loading
4. ✅ Test suite: `python src/tests/run_tests.py` (159 passing)
5. ✅ AI integration: `python src/tests/validate_ai_integration_realistic.py`

**If Issues Persist:**
1. Check Docker resources: `docker system df`
2. Clear Docker cache: `docker system prune -a`
3. Verify environment variables in `.env`
4. Check host system resources (CPU, memory, disk)
5. Review application logs for specific error patterns

### Critical System Monitoring

**Real-time Monitoring Commands:**
```bash
# Monitor all service logs
docker-compose logs -f

# Monitor specific service performance
docker-compose exec sip-server top

# Check database connectivity
docker-compose exec postgres pg_isready

# Monitor WebSocket connections
docker-compose exec sip-server netstat -an | grep :8000

# Check audio processing performance
docker-compose exec sip-server python3 -c "
from src.audio.resampler import AudioResampler
import time
resampler = AudioResampler()
start = time.perf_counter()
# Process 1000 audio frames
for i in range(1000):
    resampler.resample_audio(b'\\x00' * 160, 8000, 16000)
elapsed = (time.perf_counter() - start) * 1000
print(f'Audio processing: {elapsed:.2f}ms for 1000 frames')
"
```

### Production Deployment Verification

After any recovery, run this complete verification:

```bash
#!/bin/bash
echo "🔍 Production Verification Starting..."

# 1. Service Health
echo "1. Checking service health..."
docker-compose ps

# 2. API Endpoints
echo "2. Testing API endpoints..."
curl -s http://localhost:8080/health || echo "❌ Health check failed"
curl -s http://localhost:8080/metrics | head -5 || echo "❌ Metrics failed"

# 3. Test Suite
echo "3. Running test suite..."
python src/tests/run_tests.py

# 4. AI Integration
echo "4. Validating AI integration..."
python src/tests/validate_ai_integration_realistic.py

# 5. Audio Pipeline
echo "5. Testing audio pipeline..."
python3 -c "
from src.audio.resampler import AudioResampler
resampler = AudioResampler()
result = resampler.resample_audio(b'\\x00' * 160, 8000, 16000)
print(f'✅ Audio resampling working: {len(result)} bytes output')
"

echo "✅ Production verification complete!"
```
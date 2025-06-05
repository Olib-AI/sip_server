# 🧪 Testing Guide for Olib AI SIP Server

This guide covers the complete testing framework for the SIP server with 100% two-way AI integration.

## 📋 Table of Contents

1. [Quick Start Testing](#quick-start-testing)
2. [Test Environment Setup](#test-environment-setup)
3. [Configuration Testing](#configuration-testing)
4. [Integration Testing](#integration-testing)
5. [Docker Compose Testing](#docker-compose-testing)
6. [Component Testing](#component-testing)
7. [API Testing](#api-testing)
8. [WebSocket Testing](#websocket-testing)
9. [Performance Testing](#performance-testing)
10. [Production Testing](#production-testing)

## 🔧 Testing Framework Overview

The SIP server includes a comprehensive testing framework for the complete AI integration:

### **Implemented Test Components**

| Test Type | Purpose | Location | Status |
|-----------|---------|----------|--------|
| **Configuration Tests** | Environment & config validation | `src/tests/test_config.py` | ✅ Complete |
| **Integration Tests** | Component interaction testing | `src/tests/test_integration.py` | ✅ Complete |
| **WebSocket Tests** | Audio & bridge functionality | `src/tests/unit/test_websocket.py` | ✅ Complete |
| **Docker Tests** | Containerized testing | `docker-compose.test.yml` | ✅ Complete |
| **API Tests** | REST API endpoints | `src/tests/unit/test_api_*.py` | ✅ Implemented |
| **Load Tests** | Performance validation | `tests/load/` | ✅ Available |

### **Test Environment Types**

- **Local Development**: Direct Python testing with pytest
- **Docker Compose**: Containerized test environment with database
- **Kubernetes**: Production-like testing with MicroK8s
- **CI/CD**: Automated pipeline testing

## ⚡ Quick Start Testing

### **1. Immediate Validation**
```bash
# Quick configuration test (validates core setup)
python3 -m pytest src/tests/test_config.py::TestConfigManager::test_default_config_values -v

# Quick integration test
python3 -m pytest src/tests/test_integration.py::TestConfigurationIntegration::test_config_consistency -v

# Test Docker environment
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

### **2. Complete Test Suite**
```bash
# Run all current tests
python3 -m pytest src/tests/ -v --tb=short

# Run with coverage
python3 -m pytest src/tests/ --cov=src --cov-report=html

# Test specific components
python3 -m pytest src/tests/test_config.py -v
python3 -m pytest src/tests/test_integration.py -v
```

### **3. Docker Environment Testing**
```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run tests in container
docker-compose -f docker-compose.test.yml exec sip-server-test python3 -m pytest /app/src/tests/ -v

# Clean up
docker-compose -f docker-compose.test.yml down
```

## 🔬 Configuration Testing

### **Environment Configuration Tests**

```bash
# Test configuration loading
python3 -m pytest src/tests/test_config.py::TestConfigManager::test_default_config_values -v

# Test environment variable overrides  
python3 -m pytest src/tests/test_config.py::TestConfigManager::test_env_var_override -v

# Test boolean environment parsing
python3 -m pytest src/tests/test_config.py::TestConfigManager::test_boolean_env_vars -v

# Test configuration dictionary compatibility
python3 -m pytest src/tests/test_config.py::TestConfigManager::test_config_dict_compatibility -v
```

### **Manual Configuration Testing**

```bash
# Test configuration loading manually
python3 -c "
from src.utils.config import ConfigManager, get_config
config = get_config()
print('✅ Configuration loaded successfully')
print(f'Database: {config.database.host}:{config.database.port}')
print(f'API Port: {config.api.port}')
print(f'WebSocket Port: {config.websocket.port}')
print(f'JWT Secret: {bool(config.security.jwt_secret_key)}')
"

# Test environment variable loading
DB_HOST=test-host python3 -c "
from src.utils.config import get_config
config = get_config()
print(f'Database host override: {config.database.host}')
"
```

### **Configuration Validation**

The configuration tests validate:
- **Default Values**: All configuration has sensible defaults
- **Environment Overrides**: Environment variables properly override defaults
- **Type Conversion**: Strings converted to appropriate types (int, bool, float)
- **Dictionary Compatibility**: Backwards compatibility with dictionary access
- **Database URL Generation**: Proper PostgreSQL connection string creation

## 🔗 Integration Testing

### **Call Manager Integration**

```bash
# Test CallManager component integration
python3 -m pytest src/tests/test_integration.py::TestCallManagerIntegration -v

# Test call state management
python3 -c "
from src.call_handling.call_manager import CallManager
from unittest.mock import AsyncMock
manager = CallManager(max_concurrent_calls=10, ai_websocket_manager=AsyncMock())
print('✅ CallManager initialized successfully')
"
```

### **WebSocket Bridge Integration**

```bash
# Test WebSocket bridge initialization
python3 -m pytest src/tests/test_integration.py::TestWebSocketIntegration::test_websocket_bridge_initialization -v

# Manual WebSocket bridge testing
python3 -c "
from src.call_handling.websocket_integration import WebSocketCallBridge
from unittest.mock import MagicMock
bridge = WebSocketCallBridge(call_manager=MagicMock())
print('✅ WebSocket bridge initialized successfully')
"
```

### **Component Integration Tests**

```bash
# Test configuration integration across components
python3 -m pytest src/tests/test_integration.py::TestConfigurationIntegration::test_config_consistency -v

# Test that components use configuration correctly
python3 -m pytest src/tests/test_integration.py::TestConfigurationIntegration::test_component_configuration_usage -v
```

**Integration Test Coverage:**
- CallManager start/stop lifecycle
- WebSocket bridge initialization  
- Configuration consistency across components
- Component dependency injection
- Error handling and recovery

## 🐳 Docker Compose Testing

### **Complete Docker Environment Testing**

```bash
# Run test suite in Docker environment
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Run with isolated test database
docker-compose -f docker-compose.test.yml up --build

# Check test results
docker-compose -f docker-compose.test.yml logs sip-server-test

# Clean up test environment
docker-compose -f docker-compose.test.yml down --volumes
```

### **Docker Test Environment Details**

The `docker-compose.test.yml` provides:
- **Isolated Test Database**: PostgreSQL with test-specific configuration
- **Test-specific Ports**: Avoids conflicts (5062, 8082, 8083)
- **Environment Variables**: Loaded from `.env.test`
- **Automated Testing**: Runs pytest automatically in container

**Test Environment Configuration (`.env.test`):**
```bash
# Database
DB_HOST=postgres
DB_NAME=kamailio_test
DB_USER=kamailio
DB_PASSWORD=kamailiopw

# API ports (test-specific)
API_PORT=8082
WEBSOCKET_PORT=8083
SIP_PORT=5062

# Test configuration
TESTING=true
DEBUG=true
LOG_LEVEL=INFO
```

## 🚀 Component Testing

### **HTTP/API Load Testing**

```bash
# Comprehensive HTTP load testing
python tests/load/load_test_comprehensive.py --test comprehensive

# Specific test types
python tests/load/load_test_comprehensive.py --test ramp --rps 100 --duration 60
python tests/load/load_test_comprehensive.py --test spike --rps 200

# With authentication
python tests/load/load_test_comprehensive.py --token "your-jwt-token"
```

**HTTP Load Test Features:**
- **Ramp-up Testing**: Gradual load increase
- **Spike Testing**: Sudden traffic bursts  
- **Sustained Load**: Constant RPS over time
- **Mixed Workload**: Different endpoint combinations

### **SIP Protocol Load Testing**

```bash
# Raw SIP MESSAGE testing
python tests/load/sip_protocol_load_test.py --test mixed --count 200 --rate 10

# INVITE load testing
python tests/load/sip_protocol_load_test.py --test invite --count 100 --rate 5

# Multiple SIP methods
python tests/load/sip_protocol_load_test.py --test mixed --count 500
```

**SIP Load Test Coverage:**
- **INVITE**: Call setup performance
- **REGISTER**: Registration load
- **MESSAGE**: SMS via SIP testing
- **OPTIONS**: Keepalive testing

### **WebSocket Load Testing**

```bash
# WebSocket bridge load testing
python tests/load/websocket_bridge_load_test.py --test concurrent --connections 50

# Stress testing
python tests/load/websocket_bridge_load_test.py --test stress --connections 100

# Audio streaming performance
python tests/load/websocket_bridge_load_test.py --test ramp --connections 25 --audio-rate 50
```

**WebSocket Load Test Features:**
- **Concurrent Connections**: Up to 1000+ connections
- **Audio Streaming**: Real-time 50fps PCM simulation
- **Latency Measurement**: Round-trip time analysis
- **Connection Stability**: Long-duration testing

### **Load Test Configuration**

Edit `tests/load/load_test_config.json`:
```json
{
  "http": {
    "base_url": "http://localhost:8000",
    "auth_token": "your-token-here"
  },
  "load_test": {
    "duration": 120,
    "http_rps": 100,
    "sip_calls": 100,
    "websocket_connections": 25
  }
}
```

## 🎯 End-to-End Testing

### **Complete Call Scenarios**

```bash
# Run all E2E scenarios
python tests/e2e/end_to_end_call_tests.py --test all

# Specific scenarios
python tests/e2e/end_to_end_call_tests.py --test basic    # Basic voice call
python tests/e2e/end_to_end_call_tests.py --test dtmf     # DTMF testing
python tests/e2e/end_to_end_call_tests.py --test ai       # AI integration

# Concurrent scenario testing
python tests/e2e/end_to_end_call_tests.py --test concurrent
```

**E2E Test Scenarios:**

1. **Basic Voice Call**: Simple A-to-B calling
2. **DTMF Testing**: Digit transmission during calls
3. **Call Hold/Resume**: Hold functionality testing
4. **Call Transfer**: Transfer to third party
5. **AI Platform Integration**: WebSocket bridge testing
6. **Extended Duration**: Long-running call stability

### **E2E Test Features**

- **Audio Simulation**: PCM audio frame generation
- **WebSocket Integration**: Real AI platform connection
- **Call Quality Measurement**: MOS scoring
- **Event Logging**: Detailed call event tracking
- **Error Recovery**: Failure scenario testing

## 📊 Performance & Quality Testing

### **Call Quality Testing**

```bash
# Comprehensive call quality analysis
python tests/quality/call_quality_tests.py --test comprehensive

# Specific quality tests
python tests/quality/call_quality_tests.py --test codec     # Codec testing
python tests/quality/call_quality_tests.py --test network  # Network conditions
python tests/quality/call_quality_tests.py --test echo     # Echo cancellation
```

**Quality Test Coverage:**
- **MOS Scoring**: Mean Opinion Score calculation
- **SNR Analysis**: Signal-to-noise ratio testing
- **Codec Testing**: PCMU/PCMA quality comparison
- **Network Simulation**: Packet loss/jitter testing
- **Echo Cancellation**: Echo return loss measurement

### **DTMF Performance Testing**

```bash
# DTMF accuracy and performance
python tests/dtmf/dtmf_performance_test.py --test all

# Specific DTMF tests
python tests/dtmf/dtmf_performance_test.py --test accuracy --tests-per-digit 100
python tests/dtmf/dtmf_performance_test.py --test noise    # Noise resistance
python tests/dtmf/dtmf_performance_test.py --test timing   # Timing accuracy
```

**DTMF Test Features:**
- **Accuracy Testing**: All 16 DTMF digits (0-9, *, #, A-D)
- **Noise Resistance**: Performance under various SNR levels
- **Timing Accuracy**: Minimum duration requirements
- **Concurrent Processing**: Multi-digit simultaneous detection

### **SMS Load Testing**

```bash
# SMS system load testing
python tests/sms/sms_load_test.py --test all

# Specific SMS tests
python tests/sms/sms_load_test.py --test concurrent --messages 100
python tests/sms/sms_load_test.py --test bulk --messages 50
python tests/sms/sms_load_test.py --test sizes   # Different message lengths
```

**SMS Test Coverage:**
- **Throughput Testing**: Messages per second
- **Unicode Support**: Multi-language character testing
- **Segmentation**: Long message handling
- **SIP MESSAGE Protocol**: Raw protocol testing

## 🚢 Deployment Testing

### **Kubernetes Deployment Testing**

```bash
# Deploy to MicroK8s
./deploy-microk8s.sh

# Check deployment status
kubectl get pods -n sip-system
kubectl get services -n sip-system

# Test deployed services
kubectl port-forward -n sip-system service/sip-server-api 8000:8000 &
curl http://localhost:8000/health
```

### **Health Check Testing**

```bash
# API health endpoint
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00.000000",
  "database_connected": true,
  "kamailio_running": true,
  "websocket_bridge_active": true
}

# SIP server health
python tests/load/sip_protocol_load_test.py --test options --count 1
```

### **Database Testing**

```bash
# Connect to database
kubectl exec -it -n sip-system deployment/postgres -- psql -U kamailio -d kamailio

# Verify schema
\dt

# Check version
SELECT * FROM version;

# Add test users
INSERT INTO subscriber (username, domain, password, ha1) VALUES 
('test001', 'sip.local', 'test123', MD5('test001:sip.local:test123'));
```

### **SIP Client Testing**

**Manual SIP Client Configuration:**
1. **Download SIP Client**: Linphone, X-Lite, or Zoiper
2. **Get External IP**:
   ```bash
   EXTERNAL_IP=$(kubectl get service sip-server-sip -n sip-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
   echo "SIP Server IP: $EXTERNAL_IP"
   ```
3. **Configure Account**:
   - Username: `test001`
   - Password: `test123`
   - Domain: `$EXTERNAL_IP`
   - Port: `5060`

**SIP Testing with SIPp:**
```bash
# Install SIPp
sudo apt-get install sipp  # Linux
brew install sipp          # macOS

# Basic call test
sipp -sn uac -d 10000 -s test001 $EXTERNAL_IP:5060 -m 10 -r 1

# Load test
sipp -sn uac -d 5000 -s test001 $EXTERNAL_IP:5060 -m 100 -r 10
```

## 📈 Monitoring & Debugging

### **Real-time Monitoring**

```bash
# Monitor all pods
kubectl logs -f -n sip-system -l app=sip-server

# Monitor specific components
kubectl logs -f -n sip-system deployment/sip-server --container kamailio
kubectl logs -f -n sip-system deployment/sip-server --container api

# Resource monitoring
kubectl top pods -n sip-system
kubectl top nodes
```

### **SIP Traffic Analysis**

```bash
# Capture SIP packets
kubectl exec -n sip-system deployment/sip-server -- \
  tcpdump -i any -s 0 port 5060 -w /tmp/sip.pcap

# Copy capture file
kubectl cp sip-system/sip-server-xxx:/tmp/sip.pcap sip.pcap

# Analyze with Wireshark or tshark
tshark -r sip.pcap -Y sip
```

### **Database Monitoring**

```bash
# Check active calls
kubectl exec -it -n sip-system deployment/postgres -- \
  psql -U kamailio -d kamailio -c "SELECT * FROM dialog;"

# Check registrations
kubectl exec -n sip-system deployment/sip-server -- kamctl ul show

# Monitor database performance
kubectl exec -it -n sip-system deployment/postgres -- \
  psql -U kamailio -d kamailio -c "SELECT * FROM pg_stat_activity;"
```

### **API Monitoring**

```bash
# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/calls/active
curl http://localhost:8000/api/config/status

# Monitor API metrics (if Prometheus enabled)
curl http://localhost:8000/metrics
```

## 🔧 Troubleshooting

### **Common Issues & Solutions**

#### **1. Tests Failing**

```bash
# Check test dependencies
pip install -r requirements.txt

# Run with verbose output
python -m pytest tests/unit/test_api_calls.py -v -s

# Check test database
python scripts/init-database.py

# Clear pytest cache
rm -rf .pytest_cache __pycache__
```

#### **2. Load Tests Timeout**

```bash
# Increase timeout in configuration
edit tests/load/load_test_config.json

# Check server capacity
kubectl top pods -n sip-system

# Reduce load test intensity
python tests/load/master_load_test.py --quick
```

#### **3. SIP Registration Fails**

```bash
# Check Kamailio status
kubectl exec -n sip-system deployment/sip-server -- pgrep kamailio

# Verify database connectivity
kubectl exec -n sip-system deployment/sip-server -- \
  python3 -c "import asyncpg; print('DB OK')"

# Check SIP configuration
kubectl exec -n sip-system deployment/sip-server -- \
  kamailio -c -f /etc/kamailio/kamailio.cfg
```

#### **4. WebSocket Connection Issues**

```bash
# Check WebSocket service
kubectl get service sip-server-api -n sip-system

# Test WebSocket directly
python -c "
import asyncio
import websockets
async def test():
    async with websockets.connect('ws://localhost:8080/ws') as ws:
        print('Connected')
asyncio.run(test())
"

# Check logs
kubectl logs -n sip-system deployment/sip-server | grep websocket
```

#### **5. Database Connection Problems**

```bash
# Check PostgreSQL status
kubectl get pods -n sip-system -l app=postgres

# Test database connection
kubectl exec -it -n sip-system deployment/postgres -- \
  psql -U kamailio -d kamailio -c "SELECT version();"

# Check database logs
kubectl logs -n sip-system deployment/postgres
```

### **Performance Troubleshooting**

```bash
# Check system resources
kubectl top pods -n sip-system
kubectl describe nodes

# Check network policies
kubectl get networkpolicies -n sip-system

# Monitor during load test
watch kubectl top pods -n sip-system
```

## 🔄 CI/CD Integration

### **GitHub Actions Example**

Create `.github/workflows/test.yml`:
```yaml
name: SIP Server Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: kamailio
          POSTGRES_PASSWORD: kamailiopw
          POSTGRES_DB: kamailio
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        sudo apt-get install -y sipp
    
    - name: Run unit tests
      run: pytest tests/unit/ -v --cov=src
    
    - name: Run integration tests
      run: pytest tests/integration/ -v
    
    - name: Run load tests (quick)
      run: python tests/load/master_load_test.py --quick
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

### **Jenkins Pipeline Example**

```groovy
pipeline {
    agent any
    
    stages {
        stage('Setup') {
            steps {
                sh 'pip install -r requirements.txt'
            }
        }
        
        stage('Unit Tests') {
            steps {
                sh 'pytest tests/unit/ --junitxml=unit-results.xml'
            }
            post {
                always {
                    junit 'unit-results.xml'
                }
            }
        }
        
        stage('Integration Tests') {
            steps {
                sh 'pytest tests/integration/ --junitxml=integration-results.xml'
            }
        }
        
        stage('Load Tests') {
            steps {
                sh 'python tests/load/master_load_test.py --quick'
            }
        }
        
        stage('Deploy to Staging') {
            steps {
                sh './deploy-microk8s.sh'
            }
        }
        
        stage('E2E Tests') {
            steps {
                sh 'python tests/e2e/end_to_end_call_tests.py --test basic'
            }
        }
    }
}
```

## ✅ Success Criteria

### **Development Testing Checklist**

- [ ] **Unit Tests**: All unit tests pass (>95% coverage)
- [ ] **Integration Tests**: Component interactions work correctly  
- [ ] **Code Quality**: Linting and type checking pass
- [ ] **Security**: No secrets in code, proper authentication

### **Performance Testing Checklist**

- [ ] **API Performance**: <100ms average response time
- [ ] **SIP Performance**: <50ms call setup time
- [ ] **Throughput**: Handle 100+ concurrent calls
- [ ] **Load Testing**: System stable under 2x normal load
- [ ] **WebSocket**: <50ms audio latency
- [ ] **DTMF**: >95% detection accuracy

### **Quality Testing Checklist**

- [ ] **Call Quality**: >4.0 MOS score average
- [ ] **Audio Quality**: <1% packet loss
- [ ] **SMS Delivery**: >99% success rate
- [ ] **Error Handling**: Graceful degradation
- [ ] **Recovery**: Auto-recovery from failures

### **Production Readiness Checklist**

- [ ] **Deployment**: Successful Kubernetes deployment
- [ ] **Health Checks**: All health endpoints green
- [ ] **Monitoring**: Metrics and logging working
- [ ] **Scalability**: Auto-scaling configured
- [ ] **Security**: Network policies applied
- [ ] **Backup**: Database backup strategy tested

## 📖 Additional Resources

### **Documentation**
- [Load Testing README](tests/load/README.md) - Comprehensive load testing guide
- [API Documentation](README.md#api-documentation) - API endpoint reference
- [Architecture Overview](PROJECT_OVERVIEW.md) - System architecture

### **Test Reports**
Test execution generates detailed HTML reports:
- `load_test_results/master_load_test_report.html` - Complete load test results
- `e2e_call_test_report.html` - End-to-end call test results  
- `dtmf_performance_report.html` - DTMF performance analysis
- `call_quality_report.html` - Call quality assessment

### **Monitoring Tools**
- **Prometheus**: Metrics collection
- **Grafana**: Performance dashboards
- **Wireshark**: SIP packet analysis
- **SIPp**: SIP protocol testing

---

**🎉 When all tests pass, your SIP server is ready for production deployment and AI platform integration!**

For support and questions, refer to the troubleshooting section or check the project documentation.
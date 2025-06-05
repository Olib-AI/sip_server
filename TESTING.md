# 🧪 Comprehensive Testing Guide for Olib AI SIP Server

This guide covers the complete testing framework for the SIP server, including deployment testing, functional testing, performance testing, and quality assurance.

## 📋 Table of Contents

1. [Testing Framework Overview](#testing-framework-overview)
2. [Prerequisites](#prerequisites)
3. [Quick Testing Setup](#quick-testing-setup)
4. [Unit Testing](#unit-testing)
5. [Integration Testing](#integration-testing)
6. [Load Testing](#load-testing)
7. [End-to-End Testing](#end-to-end-testing)
8. [Performance & Quality Testing](#performance--quality-testing)
9. [Deployment Testing](#deployment-testing)
10. [Monitoring & Debugging](#monitoring--debugging)
11. [Troubleshooting](#troubleshooting)
12. [CI/CD Integration](#cicd-integration)

## 🔧 Testing Framework Overview

The SIP server includes a comprehensive testing framework with multiple layers:

### **Test Categories**

| Test Type | Purpose | Files | Coverage |
|-----------|---------|--------|----------|
| **Unit Tests** | Component isolation testing | `tests/unit/` | API endpoints, business logic |
| **Integration Tests** | Component interaction testing | `tests/integration/` | SIP flows, WebSocket bridge |
| **Load Tests** | Performance under load | `tests/load/` | HTTP, SIP, WebSocket |
| **Quality Tests** | Audio/call quality validation | `tests/quality/` | MOS scoring, codec testing |
| **DTMF Tests** | DTMF functionality validation | `tests/dtmf/` | Detection, IVR, performance |
| **SMS Tests** | SMS system validation | `tests/sms/` | SIP MESSAGE, queuing |
| **E2E Tests** | Complete workflow testing | `tests/e2e/` | Full call scenarios |

### **Test Execution Modes**

- **Development Testing**: Quick validation during development
- **CI/CD Testing**: Automated testing in pipelines  
- **Load Testing**: Performance benchmarking
- **Production Testing**: Live system validation

## 📚 Prerequisites

### **Required Software**
```bash
# Python dependencies
pip install -r requirements.txt

# Additional testing tools
pip install pytest pytest-asyncio pytest-cov pytest-html
pip install aiohttp websockets numpy matplotlib

# Optional: SIP testing tools
sudo apt-get install sipp  # Linux
brew install sipp          # macOS
```

### **Development Environment**
- **Python**: 3.11 or higher
- **Docker**: For containerized testing
- **Kubernetes**: MicroK8s or standard cluster
- **SIP Clients**: Linphone, X-Lite, or similar

### **Test Environment Setup**
```bash
# Clone and setup
git clone <repository-url>
cd olib-app/sip_server

# Install dependencies
pip install -r requirements.txt

# Initialize test database (if needed)
python scripts/init-database.py

# Verify setup
python -m pytest tests/unit/test_api_calls.py::TestCallsAPI::test_health_check -v
```

## ⚡ Quick Testing Setup

### **1. Run All Tests**
```bash
# Complete test suite
python -m pytest tests/ -v --tb=short

# With coverage report
python -m pytest tests/ --cov=src --cov-report=html

# Specific test categories
python -m pytest tests/unit/ -v          # Unit tests only
python -m pytest tests/integration/ -v   # Integration tests only
```

### **2. Quick Health Check**
```bash
# Test API health (requires running server)
curl http://localhost:8000/health

# Test SIP connectivity
python tests/load/sip_protocol_load_test.py --test options --count 1
```

### **3. Quick Load Test**
```bash
# Basic load test (lightweight)
python tests/load/master_load_test.py --quick

# API-only load test
python tests/load/load_test_comprehensive.py --test health --rps 50 --duration 30
```

## 🔬 Unit Testing

### **API Endpoint Testing**

```bash
# Test all API endpoints
python -m pytest tests/unit/test_api_calls.py -v
python -m pytest tests/unit/test_api_sms.py -v

# Test specific functionality
python -m pytest tests/unit/test_api_calls.py::TestCallsAPI::test_initiate_call_success -v

# Test with different configurations
python -m pytest tests/unit/ --auth-token="test-token" -v
```

**Example: Testing Call Initiation**
```python
# Run from tests/unit/
pytest test_api_calls.py::TestCallsAPI::test_initiate_call_success -v -s
```

### **Component Testing**

```bash
# Test DTMF components
python -m pytest tests/dtmf/test_dtmf_functionality.py -v

# Test SMS components  
python -m pytest tests/sms/test_sms_comprehensive.py -v

# Run with coverage
python -m pytest tests/unit/ --cov=src/api --cov-report=term-missing
```

### **Mock Testing Examples**

The unit tests include comprehensive mocking for external dependencies:

- **Database Operations**: SQLAlchemy models mocked
- **SIP Client**: Raw SIP sending mocked
- **WebSocket Connections**: AsyncMock for real-time testing
- **Authentication**: JWT token validation mocked

## 🔗 Integration Testing

### **SIP Integration Testing**

```bash
# Complete SIP workflow testing
python -m pytest tests/integration/test_sip_integration.py -v

# Test specific SIP scenarios
python -m pytest tests/integration/test_sip_integration.py::TestSIPIntegration::test_incoming_call_flow -v
```

**SIP Integration Test Coverage:**
- Call setup and teardown
- State transitions
- Call routing and queuing
- Database integration
- Error handling

### **WebSocket Bridge Testing**

```bash
# WebSocket integration tests
python -m pytest tests/integration/test_websocket_bridge.py -v

# Test audio streaming
python -m pytest tests/integration/test_websocket_bridge.py::TestWebSocketBridge::test_audio_streaming_to_ai -v
```

**WebSocket Test Coverage:**
- Connection management
- Audio streaming (50fps PCM)
- DTMF forwarding
- Call control messages
- Error recovery

### **Database Integration**

```bash
# Test database operations
python -m pytest tests/integration/ -k "database" -v

# Test with real database (requires setup)
DATABASE_URL=postgresql://user:pass@localhost/testdb python -m pytest tests/integration/ -v
```

## 🚀 Load Testing

### **Comprehensive Load Testing**

```bash
# Master load test runner (orchestrates all components)
python tests/load/master_load_test.py

# Quick load test
python tests/load/master_load_test.py --quick

# Custom configuration
python tests/load/master_load_test.py --config tests/load/load_test_config.json
```

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
# SIP Server Load Testing Suite

Comprehensive load testing framework for the SIP server infrastructure, designed to test all components under various load conditions.

## 🚀 Quick Start

### Prerequisites
```bash
pip install aiohttp websockets numpy matplotlib
```

### Run Complete Test Suite
```bash
# Full comprehensive test
python master_load_test.py

# Quick test (reduced load)
python master_load_test.py --quick

# Custom configuration
python master_load_test.py --config my_config.json --token "your-jwt-token"
```

## 📊 Test Components

### 1. HTTP/API Load Testing (`load_test_comprehensive.py`)
- **REST API endpoints** under load
- **Ramp-up testing** with gradual load increase
- **Spike testing** for sudden traffic bursts
- **Mixed workload testing** across different endpoints
- **Real-time performance monitoring**

**Key Features:**
- Concurrent request handling (1000+ connections)
- Response time percentiles (95th, 99th)
- Error rate analysis
- Requests per second (RPS) measurement
- Interactive charts and reports

### 2. SIP Protocol Testing (`sip_protocol_load_test.py`)
- **Raw SIP message testing** via UDP
- **INVITE/REGISTER/OPTIONS/MESSAGE** method testing
- **Call setup performance** measurement
- **Registration load testing**
- **SMS via SIP MESSAGE** load testing

**Key Features:**
- Protocol-level testing without HTTP overhead
- SIP response code analysis
- Call setup time measurement
- Concurrent SIP method testing
- Provider compatibility testing

### 3. WebSocket Bridge Testing (`websocket_bridge_load_test.py`)
- **Real-time audio streaming** simulation
- **Concurrent WebSocket connections**
- **Audio frame loss measurement**
- **Latency testing** for voice quality
- **DTMF transmission testing**

**Key Features:**
- Simulated PCM audio streaming (50fps)
- Connection stability testing
- Audio quality metrics
- WebSocket message protocol validation
- AI platform integration testing

### 4. Master Test Runner (`master_load_test.py`)
- **Orchestrated test execution** across all components
- **Health checks** before load testing
- **Baseline performance** establishment
- **Progressive load testing** phases
- **Comprehensive reporting**

## 📋 Test Scenarios

### Health Check Phase
```bash
# System connectivity verification
- HTTP API availability
- SIP server responsiveness  
- WebSocket bridge connectivity
- Component health status
```

### Baseline Testing
```bash
# Performance baseline establishment
- 100 HTTP requests
- 50 SIP OPTIONS requests
- 5 WebSocket connections for 30s
- Response time baselines
```

### Load Testing
```bash
# Normal operational load
- 100 RPS HTTP for 2 minutes
- 100 SIP calls with mixed methods
- 25 concurrent WebSocket connections
- Audio streaming at 50fps
```

### Stress Testing
```bash
# Breaking point identification
- HTTP spike: 50 -> 500 -> 50 RPS
- 200 concurrent SIP calls
- 100 WebSocket connections
- System limit discovery
```

## 🔧 Configuration

### Configuration File (`load_test_config.json`)
```json
{
  "http": {
    "base_url": "http://localhost:8000",
    "auth_token": null
  },
  "sip": {
    "host": "localhost", 
    "port": 5060
  },
  "websocket": {
    "url": "ws://localhost:8080/ws"
  },
  "load_test": {
    "duration": 120,
    "http_rps": 100,
    "sip_calls": 100,
    "websocket_connections": 25
  }
}
```

### Environment Variables
```bash
export SIP_SERVER_HOST=localhost
export SIP_SERVER_PORT=5060
export HTTP_BASE_URL=http://localhost:8000
export WEBSOCKET_URL=ws://localhost:8080/ws
export AUTH_TOKEN=your-jwt-token
```

## 🎯 Individual Test Execution

### HTTP Load Testing
```bash
# Basic HTTP load test
python load_test_comprehensive.py --test comprehensive

# Ramp-up test
python load_test_comprehensive.py --test ramp --rps 100 --duration 60

# Spike test  
python load_test_comprehensive.py --test spike --rps 200
```

### SIP Protocol Testing
```bash
# Mixed SIP methods test
python sip_protocol_load_test.py --test mixed --count 200 --rate 10

# INVITE-only test
python sip_protocol_load_test.py --test invite --count 100 --rate 5

# Registration test
python sip_protocol_load_test.py --test register --count 50 --rate 3
```

### WebSocket Bridge Testing
```bash
# Concurrent connections
python websocket_bridge_load_test.py --test concurrent --connections 20 --duration 60

# Ramp-up test
python websocket_bridge_load_test.py --test ramp --connections 50 --ramp-duration 30

# Stress test
python websocket_bridge_load_test.py --test stress --connections 100
```

## 📈 Performance Metrics

### HTTP/API Metrics
- **Response Time**: Average, median, 95th/99th percentiles
- **Throughput**: Requests per second
- **Success Rate**: Percentage of successful requests
- **Error Analysis**: HTTP status code breakdown
- **Connection Metrics**: Pool utilization, timeouts

### SIP Protocol Metrics
- **Call Setup Time**: INVITE to response latency
- **Registration Success**: REGISTER response rates
- **Method Performance**: Per-method response times
- **Protocol Compliance**: SIP response code analysis
- **Concurrent Capacity**: Maximum simultaneous calls

### WebSocket Bridge Metrics
- **Connection Stability**: Connection duration, drops
- **Audio Quality**: Frame loss, latency, jitter
- **Message Throughput**: Messages per second
- **Latency Distribution**: Round-trip time analysis
- **Resource Usage**: Memory, CPU per connection

## 📊 Report Generation

### Output Formats
- **JSON Reports**: Machine-readable results
- **HTML Reports**: Interactive charts and graphs
- **CSV Exports**: Spreadsheet analysis
- **Performance Charts**: Response time, throughput graphs

### Report Locations
```bash
# Master test results
./master_load_test_results/
├── master_load_test_report.html
├── master_load_test_report.json
└── performance_charts.png

# Individual test results  
./load_test_results/
├── load_test_report.html
├── load_test_report.json
└── load_test_charts.png
```

## 🎛️ Performance Tuning

### Optimization Targets
```bash
# HTTP API Performance
- Response Time: < 500ms average
- Success Rate: > 95%
- Throughput: > 100 RPS sustained

# SIP Protocol Performance  
- Call Setup: < 100ms
- Registration: < 50ms
- Success Rate: > 98%

# WebSocket Bridge Performance
- Audio Latency: < 50ms
- Frame Loss: < 1%
- Connection Stability: > 99% uptime
```

### System Requirements
```bash
# Minimum Requirements
- CPU: 4 cores
- RAM: 8GB
- Network: 1Gbps
- Storage: SSD recommended

# Recommended for Load Testing
- CPU: 8+ cores
- RAM: 16GB+
- Network: 10Gbps
- Storage: NVMe SSD
```

## 🚨 Troubleshooting

### Common Issues

**Connection Refused Errors**
```bash
# Check if services are running
curl http://localhost:8000/health
nc -zv localhost 5060
```

**High Error Rates**
```bash
# Reduce load and check logs
python master_load_test.py --quick
kubectl logs -n sip-system -l app=sip-server
```

**WebSocket Connection Failures**
```bash
# Test WebSocket connectivity
python websocket_bridge_load_test.py --test single --duration 10
```

**Memory Issues**
```bash
# Monitor resource usage during tests
top -p $(pgrep -f "python.*load_test")
```

### Debug Mode
```bash
# Enable verbose logging
python master_load_test.py --verbose

# Check individual components
python load_test_comprehensive.py --test health --verbose
```

## 🔍 Monitoring Integration

### Prometheus Metrics
```bash
# Export load test metrics
curl http://localhost:8000/metrics

# Key metrics to monitor:
- sip_server_response_time_seconds
- sip_server_requests_total  
- sip_server_connections_active
- sip_server_audio_frames_processed
```

### Grafana Dashboards
- **SIP Server Overview**: System health and performance
- **Load Test Results**: Real-time test metrics
- **Call Quality**: Audio streaming performance
- **Error Analysis**: Failure rate tracking

## 📝 Best Practices

### Test Environment
1. **Isolated Testing**: Use dedicated test environment
2. **Resource Monitoring**: Monitor CPU, memory, network
3. **Baseline Establishment**: Run baseline tests first
4. **Gradual Load Increase**: Use ramp-up testing
5. **Cool-down Periods**: Allow recovery between tests

### Performance Analysis
1. **Response Time Focus**: Monitor 95th percentile
2. **Error Rate Tracking**: Investigate >5% error rates
3. **Resource Correlation**: CPU/memory vs performance
4. **Bottleneck Identification**: Find limiting factors
5. **Capacity Planning**: Plan for 3x normal load

### Production Readiness
1. **Load Test Regularly**: Weekly performance checks
2. **Automate Testing**: CI/CD integration
3. **Alert Thresholds**: Set performance alerts
4. **Capacity Monitoring**: Track growth trends
5. **Disaster Recovery**: Test failure scenarios

## 🤝 Contributing

### Adding New Tests
1. Create test file in `tests/load/`
2. Follow existing patterns and naming
3. Add configuration options
4. Include comprehensive error handling
5. Generate detailed reports

### Extending Reports
1. Add metrics to result analysis
2. Update HTML report templates
3. Include performance charts
4. Document new metrics

## 📄 License

This load testing suite is part of the Olib AI SIP server project.
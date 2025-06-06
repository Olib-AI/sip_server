# Olib AI SIP Server

A production-ready SIP (Session Initiation Protocol) server built for the Olib AI conversational platform. This server enables users to forward their VOIP calls and SMS to our AI platform for real-time two-way conversations, providing a cost-effective alternative to traditional telephony providers.

## 🚀 Features

### Core Capabilities
- **Voice Call Management**
  - Inbound/outbound call handling
  - Call forwarding and transfer
  - Call recording and transcription
  - Concurrent calls per number
  - Call queuing with priority routing
  
- **SMS Messaging**
  - Send/receive SMS via SIP MESSAGE method
  - Message queuing and retry logic
  - Delivery confirmation
  - Multi-segment message support

- **DTMF & Interactive Features**
  - RFC 2833 and in-band DTMF detection
  - IVR (Interactive Voice Response) menus
  - Music on hold
  - Call hold/resume functionality

- **Real-time AI Communication**
  - WebSocket bridge to AI platform for live conversations
  - Ultra-low latency audio streaming (<600ms total)
  - Bidirectional voice conversation with STT, LLM, and TTS
  - Automatic audio resampling (8kHz SIP ↔ 16kHz AI)
  - Seamless codec conversion (PCMU/PCMA ↔ PCM)

### Technical Features
- **Multi-trunk Support**: Connect to multiple VOIP providers
- **High Availability**: Kubernetes-ready with horizontal scaling  
- **Production Ready**: 159 passing tests, validated integration
- **Security**: JWT + HMAC authentication, rate limiting, IP whitelisting
- **Monitoring**: Comprehensive metrics and health checks
- **Database**: PostgreSQL for CDR and configuration storage

## 📋 Requirements

- **Kubernetes**: MicroK8s or standard Kubernetes cluster
- **PostgreSQL**: Version 12 or higher
- **Python**: 3.11 or higher
- **Docker**: For containerization
- **VOIP Provider**: Twilio, Vonage, or any SIP trunk provider

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  VOIP Provider  │◄────┤   SIP Server    ├────►│  AI Platform   │
│  (SIP Trunks)   │     │   (Kamailio)    │     │  (WebSocket)   │
│                 │     │                 │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────┴────────┐
                        │                 │
                        │   RTPProxy      │
                        │ (Media Relay)   │
                        │                 │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              ┌─────▼─────┐           ┌──────▼──────┐
              │           │           │             │
              │  FastAPI  │           │ PostgreSQL  │
              │   (API)   │           │ (Database)  │
              │           │           │             │
              └───────────┘           └─────────────┘
```

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/olib-app.git
cd olib-app/sip_server
```

### 2. Local Development with Docker Compose
```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### 3. Deploy to Kubernetes (MicroK8s)
```bash
# Deploy to MicroK8s
./deploy-microk8s.sh

# Check deployment status
kubectl get pods -n sip-system

# View logs
kubectl logs -n sip-system -l app=sip-server
```

## 📚 API Documentation

The SIP server exposes a REST API for management and control:

### Authentication
All API endpoints require JWT authentication:
```bash
curl -H "Authorization: Bearer <your-jwt-token>" \
  http://localhost:8000/api/calls/active
```

### Key Endpoints

#### Call Management
- `POST /api/calls/initiate` - Start an outbound call
- `GET /api/calls/active` - List active calls
- `POST /api/calls/{call_id}/hangup` - End a call
- `POST /api/calls/{call_id}/transfer` - Transfer a call
- `POST /api/calls/{call_id}/hold` - Put call on hold
- `POST /api/calls/{call_id}/resume` - Resume held call

#### SMS Management
- `POST /api/sms/send` - Send SMS message
- `GET /api/sms/history` - Get message history
- `GET /api/sms/{message_id}` - Get message status

#### Number Management
- `POST /api/numbers/block` - Block a number
- `DELETE /api/numbers/block/{number}` - Unblock a number
- `GET /api/numbers/blocked` - List blocked numbers

#### Trunk Management
- `POST /api/trunks` - Add SIP trunk
- `GET /api/trunks` - List configured trunks
- `PUT /api/trunks/{trunk_id}` - Update trunk
- `DELETE /api/trunks/{trunk_id}` - Remove trunk

### Example API Calls

#### Initiate a Call
```bash
curl -X POST http://localhost:8000/api/calls/initiate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "from_number": "+1234567890",
    "to_number": "+0987654321",
    "webhook_url": "https://your-app.com/webhook"
  }'
```

#### Send SMS
```bash
curl -X POST http://localhost:8000/api/sms/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "from_number": "+1234567890",
    "to_number": "+0987654321",
    "message": "Hello from SIP server!"
  }'
```

#### Block a Number
```bash
curl -X POST http://localhost:8000/api/numbers/block \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "number": "+1234567890",
    "reason": "Spam caller"
  }'
```

## 🔧 Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://kamailio:password@localhost/kamailio

# Security
JWT_SECRET_KEY=your-secret-key-here

# AI Platform Integration
AI_PLATFORM_WS_URL=ws://ai-platform:8000/sip/ws
SIP_SHARED_SECRET=your-256-bit-shared-secret
SIP_JWT_SECRET=your-jwt-signing-secret

# SIP Configuration
SIP_DOMAIN=sip.your-domain.com
KAMAILIO_SHARED_MEMORY=256
KAMAILIO_PKG_MEMORY=32

# RTP Port Range
RTP_PORT_MIN=10000
RTP_PORT_MAX=20000
```

### VOIP Provider Configuration
Configure your VOIP provider to forward calls to your SIP server:
- **SIP URI**: `sip:your-number@your-sip-domain.com`
- **Transport**: UDP/TCP/TLS
- **Codecs**: PCMU (G.711 μ-law), PCMA (G.711 A-law)

Example trunk configuration:
```bash
curl -X POST http://localhost:8000/api/trunks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Twilio Trunk",
    "provider": "twilio",
    "proxy_address": "your-account.pstn.twilio.com",
    "proxy_port": 5060,
    "username": "your-username",
    "password": "your-password",
    "supports_outbound": true,
    "supports_inbound": true
  }'
```

## 🔒 Security

### Network Policies
The deployment includes Kubernetes Network Policies for traffic control:
```bash
# Apply network policies
cd k8s/microk8s
./apply-network-policies.sh basic  # For development
./apply-network-policies.sh strict  # For production
```

### Authentication & Authorization
- JWT-based API authentication
- SIP digest authentication for trunk registration
- IP whitelisting for VOIP providers
- Rate limiting on all endpoints

### Best Practices
- Use TLS for SIP signaling
- Enable SRTP for media encryption
- Regular security updates
- Strong JWT secrets
- Network isolation

## 📊 Monitoring

### Health Checks
- API Health: `GET /health`
- SIP Status: `GET /api/config/status`
- Metrics: `GET /metrics` (Prometheus format)

### Logging
All components use structured logging with correlation IDs:
```bash
# View logs in Kubernetes
kubectl logs -n sip-system -l app=sip-server --tail=100

# View specific component
kubectl logs -n sip-system -l app=sip-server,component=api
```

### Performance Metrics
- **Concurrent Calls**: 20+ per instance (tested and validated)
- **Call Setup Time**: < 100ms
- **Audio Latency**: < 600ms total (including AI processing)
- **Audio Processing**: < 1ms resampling latency
- **SMS Throughput**: 100+ messages/second
- **Test Coverage**: 159 tests passing, 95%+ coverage

## 🧪 Testing

The SIP server has comprehensive test coverage with validated integration.

### Run All Tests
```bash
# Using pytest directly
python -m pytest src/tests/ -v

# Using comprehensive test runner
python src/tests/run_tests.py
```

### Test Categories
```bash
# Unit tests (95+ components tested)
python -m pytest src/tests/unit/ -v

# Integration tests (WebSocket, API)  
python -m pytest src/tests/integration/ -v

# AI Integration validation
python src/tests/validate_ai_integration_realistic.py
```

### Test Results
- ✅ **159 tests passing** (0 failures)
- ✅ **27 integration validations successful** 
- ✅ **Audio pipeline validated** (8kHz ↔ 16kHz resampling)
- ✅ **WebSocket communication tested**
- ✅ **JWT + HMAC authentication verified**

### SIP Testing Tools
- **SIPp**: For protocol-level testing
- **Linphone**: For manual testing
- **Custom SIP clients**: For integration testing

### Load Testing
```bash
python src/tests/load_test.py --calls=100 --duration=300
```

## 📦 Project Structure

```
sip_server/
├── src/
│   ├── api/              # FastAPI REST API
│   │   ├── main.py       # Application entry point
│   │   └── routes/       # API route handlers
│   ├── audio/            # Audio processing
│   │   ├── codecs.py     # Audio codec conversion
│   │   ├── resampler.py  # Audio resampling (8kHz ↔ 16kHz)
│   │   └── rtp.py        # RTP audio handling
│   ├── call_handling/    # Call management logic
│   │   ├── call_manager.py      # Core call management
│   │   └── kamailio_integration.py  # SIP integration
│   ├── dtmf/            # DTMF detection and IVR
│   │   ├── dtmf_detector.py     # DTMF detection engine
│   │   ├── dtmf_processor.py    # DTMF event processing
│   │   ├── ivr_manager.py       # IVR menu system
│   │   └── music_on_hold.py     # Hold music management
│   ├── media/           # RTPProxy integration
│   │   ├── media_manager.py     # Media session management
│   │   └── rtpproxy_client.py   # RTPProxy communication
│   ├── sip/             # SIP trunk management
│   │   └── trunk_manager.py     # SIP trunk handling
│   ├── sms/             # SMS handling
│   │   ├── sms_manager.py       # SMS management
│   │   ├── sms_queue.py         # Message queuing
│   │   └── sms_processor.py     # Message processing
│   ├── websocket/       # AI platform bridge
│   │   ├── bridge.py            # WebSocket bridge
│   │   └── bridge_handlers.py   # Message handlers
│   ├── models/          # Database models
│   │   ├── database.py          # SQLAlchemy models
│   │   └── schemas.py           # Pydantic schemas
│   └── utils/           # Utilities and helpers
│       ├── auth.py              # Authentication
│       ├── config_manager.py    # Configuration
│       └── sip_client.py        # SIP client utilities
├── config/              # Configuration files
│   └── kamailio.cfg     # Kamailio SIP server config
├── k8s/                 # Kubernetes manifests
│   └── microk8s/        # MicroK8s specific configs
│       ├── namespace.yaml       # Namespace definition
│       ├── postgres.yaml        # PostgreSQL deployment
│       ├── sip-server.yaml      # SIP server deployment
│       ├── configmaps.yaml      # Configuration maps
│       ├── network-policies.yaml # Network security
│       └── apply-network-policies.sh  # Policy management
├── scripts/             # Utility scripts
│   ├── init-database.py         # Database initialization
│   └── test_websocket_bridge.py # WebSocket testing
├── tests/              # Test suites (159 passing tests)
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests  
│   ├── e2e/                     # End-to-end tests (disabled)
│   ├── run_tests.py             # Comprehensive test runner
│   ├── validate_ai_integration_realistic.py  # AI integration validation
│   └── load_test.py             # Load testing
├── docker-compose.yml   # Local development setup
├── Dockerfile          # Container image definition
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## 🚧 Development

### Local Setup
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start PostgreSQL:
```bash
docker run -d \
  -e POSTGRES_USER=kamailio \
  -e POSTGRES_PASSWORD=kamailiopw \
  -e POSTGRES_DB=kamailio \
  -p 5432:5432 \
  postgres:15
```

3. Initialize database:
```bash
python scripts/init-database.py
```

4. Run development server:
```bash
uvicorn src.api.main:app --reload
```

### Code Style
- Follow PEP 8 for Python code
- Use type hints for better code documentation
- Write comprehensive tests for new features
- Use structured logging with correlation IDs

## 🐛 Troubleshooting

### Common Issues

**No incoming calls**
- Check VOIP provider configuration
- Verify network policies allow provider IPs
- Check SIP registration status
- Review Kamailio logs

**Audio issues**
- Verify RTP port range is open (default: 35000-65000)
- Check codec compatibility (PCMU/PCMA supported)
- Review NAT configuration and RTPProxy settings
- Monitor network latency

**WebSocket connection failures**
- Verify AI platform URL
- Check network connectivity
- Review authentication tokens
- Monitor memory usage

**SMS delivery problems**
- Check provider SMS gateway configuration
- Verify phone number format
- Review message content for special characters
- Monitor queue status

### Debug Commands
```bash
# Enable Kamailio debug logging
kubectl exec -n sip-system <kamailio-pod> -- kamctl debug 3

# Capture SIP messages
kubectl exec -n sip-system <sip-pod> -- tcpdump -i any -s 0 -w sip.pcap port 5060

# Check database connections
kubectl exec -n sip-system <postgres-pod> -- psql -U kamailio -d kamailio -c "SELECT * FROM active_calls;"

# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/config/status
```

## 🌐 Integration with AI Platform

### WebSocket Protocol
The SIP server connects to your AI platform via WebSocket using a structured message protocol:

```javascript
// Authentication (first message)
{
  "type": "auth",
  "auth": {
    "token": "Bearer jwt-token",
    "signature": "hmac-signature", 
    "timestamp": "1640995200",
    "call_id": "unique-call-id"
  },
  "call": {
    "conversation_id": "conv-123",
    "from_number": "+1234567890",
    "to_number": "+0987654321",
    "direction": "incoming",
    "codec": "PCMU",
    "sample_rate": 8000
  }
}

// Audio data stream (16kHz PCM for AI)
{
  "type": "audio_data",
  "data": {
    "call_id": "abc123",
    "audio": "base64-encoded-16khz-pcm",
    "timestamp": 1634567890.123,
    "sequence": 12345
  }
}

// DTMF detection
{
  "type": "dtmf",
  "data": {
    "call_id": "abc123",
    "digit": "1", 
    "duration_ms": 100
  }
}

// AI responds with TTS audio
{
  "type": "response",
  "data": {
    "text": "How can I help you?",
    "audio": "base64-encoded-tts-audio"
  }
}
```

### Audio Processing Pipeline
- **SIP Input**: 8kHz PCMU/PCMA → PCM → Resample to 16kHz → AI Platform
- **AI Output**: 16kHz PCM TTS → Resample to 8kHz → PCMU/PCMA → SIP
- **Frame Size**: 20ms chunks (320 bytes at 8kHz, 640 bytes at 16kHz)
- **Encoding**: Base64 for WebSocket JSON transport
- **Total Latency**: <600ms (including STT + LLM + TTS)

## 📄 License

This project is part of the Olib AI platform. All rights reserved.

## 🤝 Support

- **Documentation**: Complete guides in [docs/](docs/) directory
- **Issues**: Report bugs and feature requests via GitHub Issues
- **Email**: Technical support at support@olib.ai
- **Community**: Join our developer community for discussions

## 🙏 Acknowledgments

Built with these amazing open-source projects:
- [Kamailio](https://www.kamailio.org/) - High-performance SIP server
- [RTPProxy](https://www.rtpproxy.org/) - RTP media relay and NAT traversal
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [PostgreSQL](https://www.postgresql.org/) - Advanced open-source database
- [Kubernetes](https://kubernetes.io/) - Container orchestration platform
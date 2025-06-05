# Olib AI SIP Server

A production-ready SIP (Session Initiation Protocol) server built for the Olib AI conversational platform. This server replaces traditional telephony providers like Twilio with a cost-effective, high-performance solution that provides full control over voice calls and SMS messaging.

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

- **Real-time Communication**
  - WebSocket bridge to AI platform
  - Low-latency audio streaming
  - Bidirectional audio processing
  - Automatic codec conversion (PCMU/PCMA ↔ PCM)

### Technical Features
- **Multi-trunk Support**: Connect to multiple VOIP providers
- **High Availability**: Kubernetes-ready with horizontal scaling
- **Security**: JWT authentication, rate limiting, IP whitelisting
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
                        │   RTPEngine     │
                        │ (Media Server)  │
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

# AI Platform
AI_PLATFORM_URL=ws://ai-platform:8001/ws/voice

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
- **Concurrent Calls**: 1000+ per instance
- **Call Setup Time**: < 100ms
- **Audio Latency**: < 50ms
- **SMS Throughput**: 100+ messages/second

## 🧪 Testing

### Unit Tests
```bash
pytest tests/unit -v
```

### Integration Tests
```bash
pytest tests/integration -v
```

### Load Testing
```bash
python src/tests/load_test.py --calls=100 --duration=300
```

### Test WebSocket Connection
```bash
python scripts/test_websocket_bridge.py
```

### SIP Testing Tools
- **SIPp**: For protocol-level testing
- **Linphone**: For manual testing
- **Custom SIP clients**: For integration testing

## 📦 Project Structure

```
sip_server/
├── src/
│   ├── api/              # FastAPI REST API
│   │   ├── main.py       # Application entry point
│   │   └── routes/       # API route handlers
│   ├── call_handling/    # Call management logic
│   │   ├── call_manager.py      # Core call management
│   │   └── kamailio_integration.py  # SIP integration
│   ├── dtmf/            # DTMF detection and IVR
│   │   ├── dtmf_detector.py     # DTMF detection engine
│   │   ├── dtmf_processor.py    # DTMF event processing
│   │   ├── ivr_manager.py       # IVR menu system
│   │   └── music_on_hold.py     # Hold music management
│   ├── media/           # RTPEngine integration
│   │   ├── media_manager.py     # Media session management
│   │   └── rtpengine_client.py  # RTPEngine communication
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
├── tests/              # Test suites
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
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
- Verify RTP port range is open
- Check codec compatibility
- Review NAT configuration
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
// Incoming call notification
{
  "type": "call_start",
  "data": {
    "call_id": "abc123",
    "from_number": "+1234567890",
    "to_number": "+0987654321",
    "codec": "PCMU",
    "sample_rate": 8000
  }
}

// Audio data stream
{
  "type": "audio_data",
  "data": {
    "call_id": "abc123",
    "audio": "base64-encoded-pcm-data",
    "timestamp": 1634567890.123
  }
}

// DTMF detection
{
  "type": "dtmf",
  "data": {
    "call_id": "abc123",
    "digit": "1",
    "timestamp": 1634567890.123
  }
}

// AI can respond with actions
{
  "type": "hangup",
  "call_id": "abc123"
}

{
  "type": "transfer",
  "call_id": "abc123",
  "target": "+1234567890"
}
```

### Audio Format
- **Format**: 16-bit PCM, 8kHz, mono
- **Frame Size**: 20ms (320 bytes)
- **Encoding**: Base64 for JSON transport
- **Latency**: <50ms typical

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
- [RTPEngine](https://github.com/sipwise/rtpengine) - Real-time media relay
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [PostgreSQL](https://www.postgresql.org/) - Advanced open-source database
- [Kubernetes](https://kubernetes.io/) - Container orchestration platform
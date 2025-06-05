# Olib AI SIP Server Project Overview

## Project Purpose
This project implements a fully integrated SIP (Session Initiation Protocol) server with 100% two-way integration to the Olib AI conversational platform. The system provides:
- Complete replacement for Twilio with cost reduction
- Ultra-low latency real-time bidirectional communication
- Full control over call handling, audio processing, and AI integration
- Advanced SMS and call management capabilities
- Production-ready containerized deployment

## Architecture Overview

### Core Components
1. **SIP Server (Kamailio)**: Advanced SIP signaling with Kamailio integration for state synchronization
2. **Media Processing**: RTP media relay with codec conversion (μ-law, A-law, PCM)
3. **WebSocket Bridge**: Real-time bidirectional AI platform integration with authentication
4. **API Server**: Complete REST API suite for call/SMS management and configuration
5. **Call Manager**: Centralized call state management with DTMF and IVR support
6. **SMS Integration**: SIP MESSAGE protocol support for text messaging
7. **Database**: PostgreSQL with comprehensive call/SMS logging
8. **Configuration System**: Environment-based configuration with .env support

### Integration Flow
```
User Phone → VOIP Provider → SIP Server (Kamailio) → Call Manager → WebSocket Bridge → AI Platform
                                    ↓                      ↓              ↑
                              RTP Media Relay     Audio Processing    Real-time Response
                                    ↓                      ↓              ↓
                              Codec Conversion       DTMF/IVR      State Synchronization
```

## Implemented Features ✅
- **Complete Call Handling**: Full inbound/outbound call lifecycle management
- **Real-time Audio Streaming**: Low-latency audio with codec conversion
- **WebSocket Authentication**: JWT and API key authentication for secure connections
- **Advanced Call Management**: State synchronization, transfer, hold, DTMF processing
- **SMS Integration**: Full SMS send/receive with SIP MESSAGE protocol
- **Configuration Management**: Environment-based configuration with hot reload
- **Audio Pipeline**: Multi-codec support (μ-law, A-law, PCM) with resampling
- **Call State Sync**: Bidirectional state synchronization with Kamailio
- **IVR Support**: Interactive Voice Response with music on hold
- **API Suite**: Complete REST APIs for all operations
- **Database Integration**: Comprehensive logging and state persistence
- **Docker Deployment**: Production-ready containerized environment

## Technology Stack
- **SIP Server**: Kamailio 6.0+ with custom routing logic
- **Media Processing**: RTPProxy with Python audio processing
- **Programming Language**: Python 3.12 with async/await architecture
- **WebSocket**: Real-time bidirectional communication with authentication
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Audio Processing**: NumPy/SciPy for codec conversion and resampling
- **Authentication**: JWT tokens and API key validation
- **Configuration**: Environment variables with .env file support
- **Container**: Docker with Alpine Linux (production-optimized)
- **Testing**: Pytest with async support and comprehensive test suite

## Deployment Model
- Containerized using Docker
- Deployed as Kubernetes Deployment
- Exposed via LoadBalancer service (custom plugin for SIP ports)
- Horizontally scalable for high availability

## Customer Integration
1. Customers register with VOIP providers (Twilio, Vonage, etc.)
2. Configure VOIP provider to forward calls to our SIP server address
3. Our system handles the call and connects to AI platform
4. AI processes the conversation and sends responses back

## Advantages Over Twilio
- **Cost**: Significantly lower per-minute rates
- **Performance**: Direct SIP handling reduces latency
- **Control**: Full control over call flow and features
- **Scalability**: Can handle thousands of concurrent calls
- **Customization**: Tailored for our AI platform needs

## Security Considerations
- SIP authentication for registered users
- TLS encryption for SIP signaling
- SRTP for encrypted media streams
- API authentication using JWT tokens
- Rate limiting and DDoS protection
# Olib AI SIP Server Project Overview

## Project Purpose
This project implements a custom SIP (Session Initiation Protocol) server to replace Twilio for handling voice calls and SMS in the Olib AI conversational platform. The system is designed to:
- Reduce costs compared to Twilio
- Improve call latency and quality
- Provide full control over call handling and routing
- Support concurrent calls per number
- Enable real-time bidirectional communication with the AI platform

## Architecture Overview

### Core Components
1. **SIP Server (Kamailio)**: Handles SIP signaling, registration, and call routing
2. **Media Server (RTPEngine)**: Manages RTP media streams for voice data
3. **WebSocket Bridge**: Connects SIP calls to the AI platform via WebSocket
4. **API Server**: Provides REST APIs for call management, SMS, and configuration
5. **Database**: Stores call records, configurations, and blocked numbers

### Integration Flow
```
User Phone → VOIP Provider → Our SIP Server → WebSocket → AI Platform
                                    ↓
                              Media Server (RTP)
```

## Key Features
- **Incoming Call Handling**: Accept calls from VOIP providers
- **Outgoing Call Support**: Initiate calls via API
- **Call Forwarding**: Route calls to other numbers
- **Call Triage**: Intelligent call routing based on AI decisions
- **SMS Support**: Send/receive SMS messages
- **DTMF Support**: Handle touch-tone inputs during calls
- **Number Blocking**: Manage blocked numbers via API
- **Concurrent Calls**: Multiple simultaneous calls per number
- **Real-time Audio**: Low-latency audio streaming to AI platform

## Technology Stack
- **SIP Server**: Kamailio 5.7.x
- **Media Server**: RTPEngine
- **Programming Language**: Python 3.11 (API server and WebSocket bridge)
- **WebSocket**: For AI platform communication
- **Database**: PostgreSQL (for persistence)
- **Container**: Docker with Alpine Linux
- **Orchestration**: Kubernetes-ready

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
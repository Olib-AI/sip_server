# Wholesale SIP Provider Integration Guide

Complete step-by-step guide to integrate wholesale SIP providers with the Olib AI SIP Server for two-way calls and SMS at wholesale termination rates.

## 🎯 Overview

This integration provides:
- **Ultra-low cost voice**: $0.001-0.005/minute wholesale termination rates
- **Two-way calling**: Inbound and outbound calls through your SIP infrastructure
- **Database-driven**: All trunk configurations stored in database, no ENV variables
- **Phone numbers**: Get DID numbers from wholesale providers
- **Production ready**: Works with existing SIP infrastructure

## 📋 Prerequisites

- Wholesale SIP provider account (Skyetel, DIDForSale, etc.)
- Domain name for SIP endpoints (e.g., `sip.yourdomain.com`)
- SSL certificate for secure SIP (TLS) - optional
- Olib AI SIP server deployed and accessible

## 🚀 Step 1: Wholesale Provider Setup

### 1.1 Choose Your Wholesale Provider
**Recommended providers for cost-effectiveness:**

**Skyetel** - Ultra-competitive rates
- Website: https://www.skyetel.com
- DID numbers: $1/month  
- Termination: $0.001-0.005/minute
- Features: SIP trunking, SMS, instant provisioning

**DIDForSale** - Wholesale specialist
- Website: https://www.didforsale.com  
- Focus: Wholesale SIP trunking
- Features: Bulk pricing, global coverage

### 1.2 Get Account Credentials
```bash
# From your provider's portal:
# Username: your_sip_username
# Password: your_sip_password  
# SIP Domain: sip.provider.com
# Note these down - you'll need them for trunk creation
```

## 📞 Step 2: Purchase DID Numbers

### 2.1 Buy DID Numbers from Wholesale Provider
**Skyetel Example:**
```bash
# Login to Skyetel Portal
# 1. Go to Phone Numbers → Purchase
# 2. Select country/area code (US recommended)
# 3. Choose numbers with voice capabilities
# 4. Purchase for ~$1/month each
# 5. Configure to point to your SIP server IP
```

**DIDForSale Example:**
```bash
# Login to DIDForSale Portal  
# 1. Browse available numbers
# 2. Select numbers with voice/SMS support
# 3. Purchase in bulk for better rates
# 4. Configure forwarding to your infrastructure
```

### 2.2 Configure Number Routing
```bash
# Point your DID numbers to your SIP server:
# SIP URI: sip:your_sip_domain.com:5060
# IP Address: your_server_public_ip:5060
# Protocol: UDP/TCP (based on your preference)
```

## 🔧 Step 3: Configure Provider-Side Routing

### 3.1 Skyetel Configuration
```bash
# In Skyetel Portal:
# 1. Go to Endpoints → SIP Endpoints
# 2. Add your server IP: your_server_ip:5060
# 3. Set authentication (if required)
# 4. Configure number routing to your endpoint
```

### 3.2 DIDForSale Configuration  
```bash
# In DIDForSale Portal:
# 1. Configure SIP termination settings
# 2. Add destination: sip:your_server_ip:5060
# 3. Set failover options (optional)
# 4. Test connectivity
```

### 3.3 Provider Authentication Setup
```bash
# Most wholesale providers use IP authentication
# Add your server's public IP to provider's whitelist:
# Example IPs to whitelist: 123.456.789.0/24
# Some may require username/password authentication
```

## ⚙️ Step 4: Add Trunk to Database

### 4.1 Add Wholesale Provider Trunk via API
Now you simply add your wholesale trunk to the database - no environment variables needed!

```bash
# Example: Add Skyetel trunk (replace with your actual provider)
curl -X POST http://localhost:8080/api/trunks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-jwt-token>" \
  -d '{
    "trunk_id": "skyetel_main",
    "name": "Skyetel Main Trunk",
    "provider": "skyetel",
    "proxy_address": "sip.skyetel.com",
    "proxy_port": 5060,
    "username": "your_skyetel_username",
    "password": "your_skyetel_password",
    "realm": "sip.skyetel.com",
    "supports_outbound": true,
    "supports_inbound": true,
    "transport": "UDP",
    "preferred_codecs": ["PCMU", "PCMA"],
    "max_concurrent_calls": 100,
    "calls_per_second_limit": 10
  }'
```

### 4.2 Alternative: Add DIDForSale trunk
```bash
curl -X POST http://localhost:8080/api/trunks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-jwt-token>" \
  -d '{
    "trunk_id": "didforsale_main",
    "name": "DIDForSale Trunk",
    "provider": "didforsale",
    "proxy_address": "sip.didforsale.com", 
    "proxy_port": 5060,
    "username": "your_did_username",
    "password": "your_did_password",
    "supports_outbound": true,
    "supports_inbound": true,
    "transport": "UDP",
    "preferred_codecs": ["PCMU", "PCMA"]
  }'
```

### 4.3 Verify Trunk Creation
```bash
# List all trunks
curl -H "Authorization: Bearer <your-jwt-token>" \
  http://localhost:8080/api/trunks

# Get specific trunk
curl -H "Authorization: Bearer <your-jwt-token>" \
  http://localhost:8080/api/trunks/skyetel_main

# Activate trunk
curl -X POST -H "Authorization: Bearer <your-jwt-token>" \
  http://localhost:8080/api/trunks/skyetel_main/activate
```

## 📨 Step 5: SMS Integration (Optional)

### 5.1 Provider SMS Configuration
**Note**: SMS handling varies by wholesale provider. Some offer SIP MESSAGE support, others use HTTP APIs.

**Skyetel SMS:**
```bash
# Skyetel supports SMS via SIP MESSAGE protocol
# Your existing SMS manager should work automatically
# Configure in provider portal to enable SMS routing
```

**Alternative SMS Providers:**
```bash
# If your wholesale provider doesn't support SMS:
# Consider dedicated SMS providers:
# - Telnyx: $0.004/message
# - Bandwidth: $0.0035/message  
# - Plivo: $0.0035/message
```

### 5.2 SIP MESSAGE Handler (Existing)
Your SIP server already handles SMS via SIP MESSAGE protocol:

```bash
# SMS automatically works through existing routes:
# POST /api/sms/send - Send SMS
# GET /api/sms/history - SMS history
# Webhook handling built into SIP MESSAGE processing
```

### 5.3 Test SMS Functionality
```bash
# Send test SMS through your API:
curl -X POST http://localhost:8080/api/sms/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "from_number": "+15551234567",
    "to_number": "+19876543210", 
    "message": "Test SMS from Olib AI SIP Server!"
  }'
```

## 🧪 Step 6: Testing Two-Way Calls

### 6.1 Test Inbound Calls
```bash
# Call your DID number from any phone
# Expected flow:
# 1. Call reaches wholesale provider
# 2. Provider forwards to your SIP server (via IP routing)
# 3. Your server processes call
# 4. AI platform receives audio via WebSocket
# 5. AI responds with TTS  
# 6. Audio flows back to caller

# Monitor logs:
kubectl logs -n sip-system -l app=sip-server --tail=100 -f
```

### 6.2 Test Outbound Calls
```bash
# Make outbound call via API:
curl -X POST http://localhost:8080/api/calls/initiate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "from_number": "+15551234567",
    "to_number": "+19876543210",
    "webhook_url": "https://yourdomain.com/call-webhook"
  }'

# Expected flow:
# 1. API call triggers outbound call
# 2. SIP server connects to wholesale trunk
# 3. Provider routes call to PSTN
# 4. Audio flows bidirectionally
# 5. AI processes conversation
```

### 6.3 Test Trunk Status
```bash
# Check trunk connectivity:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/trunks/skyetel_main/status

# Monitor call statistics:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/trunks/stats/summary

# View active calls:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/calls/active
```

## 🔒 Step 7: Security Configuration

### 7.1 IP Allowlisting (Provider Side)
```bash
# Most wholesale providers use IP authentication
# Add your server IPs to provider's whitelist:

# Skyetel Portal:
# 1. Go to Security → IP Access Control
# 2. Add your server's public IP: 123.456.789.0/24
# 3. Apply to both incoming and outgoing traffic

# DIDForSale Portal:
# 1. Configure IP authentication
# 2. Add server IP ranges
# 3. Set geographic restrictions if needed
```

### 7.2 Trunk-Level Security
```bash
# Update trunk with security settings:
curl -X PUT http://localhost:8080/api/trunks/skyetel_main \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "allowed_ips": ["provider.ip.range.0/24"],
    "transport": "TLS",
    "auth_method": "digest"
  }'
```

### 7.3 Network-Level Security
```bash
# Firewall rules for your SIP server:
# Allow SIP signaling: port 5060 (UDP/TCP)
# Allow RTP media: ports 10000-20000 (UDP)
# Restrict to provider IP ranges only

# Example iptables rules:
iptables -A INPUT -p udp --dport 5060 -s provider_ip_range -j ACCEPT
iptables -A INPUT -p udp --dport 10000:20000 -s provider_ip_range -j ACCEPT
```

## 📊 Step 8: Monitoring & Troubleshooting

### 8.1 Call Detail Records
```bash
# Monitor call quality and costs:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/calls/cdr?provider=twilio&limit=100
```

### 8.2 Real-time Monitoring
```bash
# View active calls:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/calls/active

# Check trunk status:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/trunks/status
```

### 8.3 Debug Common Issues

**No Incoming Calls:**
```bash
# Check Twilio webhook URL is accessible:
curl -X POST https://sip.yourdomain.com/twilio/webhook \
  -d "From=+15551234567&To=+19876543210"

# Verify IP allowlisting in Twilio Console
# Check Kamailio logs for SIP messages
```

**Poor Audio Quality:**
```bash
# Check codec negotiation:
# Ensure PCMU/PCMA are enabled on both sides
# Monitor RTP packet loss and jitter
# Verify firewall allows RTP port range (10000-20000)
```

**SMS Not Working:**
```bash
# Test webhook endpoint:
curl -X POST https://sip.yourdomain.com/api/sms/twilio/webhook \
  -d "From=+15551234567&To=+19876543210&Body=Test&MessageSid=test123"

# Check Twilio webhook logs in Console
# Verify SMS webhook URL configuration
```

## 💰 Cost Analysis

### Wholesale Provider Rates (2024)
**Skyetel:**
- **Voice termination**: $0.001-0.003/minute (US domestic)
- **Voice origination**: $0.001-0.003/minute (US domestic)  
- **SMS**: $0.004/message (US)
- **DID number rental**: $1.00/month (US local)

**DIDForSale:**
- **Voice termination**: $0.001-0.005/minute (US domestic)
- **Bulk discounts**: Available for high volume
- **DID numbers**: $1-3/month (based on location)

### Cost Comparison vs Retail Providers
- **Twilio Programmable Voice**: $0.0085/min (300-850% more expensive)
- **Vonage Business**: $0.02-0.05/min (600-5000% more expensive)
- **RingCentral**: $0.03-0.10/min (1000-10000% more expensive)
- **Traditional carriers**: $0.05-0.25/min (1600-25000% more expensive)

**Result**: Wholesale providers offer 70-95% cost savings with your own SIP infrastructure.

## 🎉 Step 9: Production Deployment

### 9.1 Scale Considerations
```bash
# Configure trunk limits per provider:
curl -X PUT http://localhost:8080/api/trunks/skyetel_main \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "max_concurrent_calls": 1000,
    "calls_per_second_limit": 50
  }'
```

### 9.2 Failover Configuration
```bash
# Add backup wholesale trunks:
curl -X POST http://localhost:8080/api/trunks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "trunk_id": "didforsale_backup",
    "name": "DIDForSale Backup Trunk",
    "provider": "didforsale",
    "proxy_address": "backup.didforsale.com",
    "proxy_port": 5060,
    "username": "backup_username",
    "password": "backup_password",
    "backup_trunks": ["skyetel_main"]
  }'
```

### 9.3 Health Monitoring
```bash
# Monitor trunk health:
curl -H "Authorization: Bearer <token>" \
  http://localhost:8080/api/trunks/stats/summary

# Set up alerts based on metrics:
# - Success rate < 95%
# - Failed calls > 100/hour  
# - Trunk registration failures

# Example Prometheus metrics:
sip_trunk_registration_status{provider="skyetel"} 1
sip_calls_total{provider="skyetel",status="success"} 1542
sip_call_duration_seconds{provider="skyetel"} 180.5
sip_trunk_cost_per_minute{provider="skyetel"} 0.002
```

## ✅ Verification Checklist

- [ ] Wholesale provider account created and verified
- [ ] DID numbers purchased with voice capability
- [ ] Provider-side routing configured to your SIP server
- [ ] IP authentication configured on provider side
- [ ] Trunk added to database via API
- [ ] Trunk activated and status verified
- [ ] Inbound calls working from DID numbers
- [ ] Outbound calls working through trunk
- [ ] SMS working (if supported by provider)
- [ ] Security measures implemented (IP restrictions)
- [ ] Monitoring configured and alerts set
- [ ] Backup trunks configured for failover
- [ ] Production deployment ready

## 📞 Support

**Wholesale Provider Support:**
- **Skyetel Support**: https://skyetel.com/support
- **DIDForSale Support**: https://didforsale.com/support
- **Provider Documentation**: Check each provider's portal

**SIP Server Support:**
- **Olib AI Documentation**: Complete guides in docs/ directory
- **API Reference**: Built-in OpenAPI docs at /docs endpoint
- **Database CRUD**: All trunk configurations in database
- **Real-time Monitoring**: Comprehensive metrics and logging

**Integration Complete!** Your Olib AI SIP Server now has ultra-low-cost two-way calling through wholesale SIP providers with 70-95% cost savings over retail providers.
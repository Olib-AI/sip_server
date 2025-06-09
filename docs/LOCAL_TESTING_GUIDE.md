# Local SIP Server Testing Guide with Linphone

This guide shows you how to test your Olib AI SIP Server locally using Linphone. Linphone is the perfect choice for development and testing because it provides detailed debugging information, supports all SIP features, and works reliably across platforms.

## 🚀 Quick Start

### Prerequisites
- macOS computer
- Docker and Docker Compose installed
- Olib AI SIP Server repository cloned

## 📱 Why Linphone?

**Linphone** is the ideal SIP client for testing because it offers:
- ✅ **Advanced debugging**: Detailed logs and network information
- ✅ **All SIP features**: DTMF, transfers, hold/resume, multiple accounts
- ✅ **Codec flexibility**: PCMU, PCMA, G722, Opus, and more
- ✅ **Cross-platform**: Test on macOS, iOS, Android, Windows, Linux
- ✅ **Free and open source**: No limitations for testing
- ✅ **Professional grade**: Used in production environments

### Download Linphone
- **macOS**: [Download from linphone.org](https://www.linphone.org/technical-corner/linphone/downloads)
- **Alternative**: Install via Homebrew: `brew install --cask linphone`

## 🛠️ Step-by-Step Setup

### Step 1: Start the SIP Server

```bash
# Navigate to the project directory
cd olib-app/sip_server

# Copy environment file if not already done
cp example.env .env

# Start all services
docker compose up -d

# Verify services are running
docker compose ps

# Check logs
docker compose logs -f sip-server
```

### Step 2: Create Test Users

The repository includes a setup script for creating test users. Simply run:

```bash
# Make sure the script is executable (should already be)
chmod +x setup_test_users.sh

# Run the setup script
./setup_test_users.sh
```

The script will:
- ✅ Generate an admin JWT token
- ✅ Create 3 test users (test1, test2, test3)
- ✅ Display your server's IP address for mobile testing
- ✅ Show configuration details for Linphone

**Expected output:**
```
🚀 Setting up local SIP testing environment...
✓ Admin token generated
Creating test users...
✓ User test1 created
✓ User test2 created
✓ User test3 created

✅ Setup complete!

📱 SIP Client Configuration:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Server: localhost or 192.168.1.100
Port: 5060
Transport: UDP or TCP

Test Users:
• Username: test1 | Password: password1
• Username: test2 | Password: password2
• Username: test3 | Password: password3

🎯 To test calls:
1. Register two users in different SIP clients
2. Call using: test2@localhost or test2@192.168.1.100
```

**Troubleshooting the script:**
```bash
# If script fails, check if services are running
docker compose ps

# Check if API is accessible
curl http://localhost:8080/health

# Manually create a user if needed
ADMIN_TOKEN=$(docker compose exec sip-server python -c "
from src.utils.auth import create_access_token
from datetime import timedelta
print(create_access_token(data={'sub': 'admin', 'role': 'admin'}, expires_delta=timedelta(days=1)))
")

curl -X POST http://localhost:8080/api/sip-users/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "username": "test1",
    "password": "password1",
    "display_name": "Test User 1",
    "realm": "localhost"
  }'
```

### Step 3: Configure Linphone

#### Initial Setup

1. **Launch Linphone**
   - Open Linphone from Applications
   - If prompted for account setup, choose **Use SIP account**

2. **Create First SIP Account**:
   - Click **Settings** (gear icon) or go to **Linphone** → **Preferences**
   - Select **Network** → **SIP Accounts**
   - Click **Add** (+ button)

3. **Account Configuration**:
   ```
   Identity:
   ├── Username: test1
   ├── Display name: Test User 1
   ├── SIP Address: test1@localhost
   └── Password: password1

   Network:
   ├── SIP server address: localhost
   ├── SIP server port: 5060
   ├── Transport: UDP (or TCP if needed)
   └── Outbound proxy: (leave empty)

   Advanced:
   ├── Registration duration: 3600 seconds
   ├── Publish presence: No
   └── Enable ICE: No (for local testing)
   ```

4. **Save Account**:
   - Click **OK** to save
   - Account should appear in the accounts list
   - Check for green status indicator (registered)

#### Configure Second Account for Testing

1. **Add Second Account**:
   - Click **Add** again in SIP Accounts
   - Configure similar to first account:
   ```
   Username: test2
   Display name: Test User 2
   SIP Address: test2@localhost
   Password: password2
   SIP server address: localhost
   ```

2. **Switch Between Accounts**:
   - In main Linphone window, use the account dropdown
   - Select which account to use for outgoing calls

### Step 4: Set Up Second Linphone Instance

For testing calls between users, you have several options:

#### Option A: Multiple Accounts in Same Linphone
- Use the account switcher in Linphone's main window
- Switch accounts to make calls between test1 and test2

#### Option B: Second Device with Linphone
1. **Install Linphone on mobile device** (iOS/Android)
2. **Get your Mac's IP address**:
   ```bash
   ipconfig getifaddr en0  # Usually something like 192.168.1.100
   ```
3. **Configure mobile Linphone**:
   ```
   Username: test2
   Display name: Test User 2
   SIP server address: 192.168.1.100  # Your Mac's IP
   Password: password2
   ```

#### Option C: Second Linphone Instance (Advanced)
For simultaneous testing, you can run multiple Linphone instances:
```bash
# Create separate config directory
mkdir ~/linphone-test2
# Launch second instance with different config
/Applications/Linphone.app/Contents/MacOS/Linphone --config-dir ~/linphone-test2
```

### Step 5: Make Test Calls with Linphone

#### Basic Call Testing

1. **Make a Call**:
   - Select `test1` account in Linphone
   - In the dial pad, enter: `test2@localhost` or just `test2`
   - Click the green **Call** button
   - You should see "Calling..." status

2. **Answer the Call**:
   - Switch to `test2` account (or use second device)
   - Accept the incoming call
   - You should hear audio between both clients

3. **During Call Testing**:
   - **Hold/Resume**: Click hold button and resume
   - **DTMF**: Use dial pad during call to send tones
   - **Mute/Unmute**: Test microphone controls
   - **Speaker**: Test speaker on/off

#### Advanced Linphone Features

1. **Call Transfer**:
   - During active call, click **Transfer**
   - Enter `test3@localhost`
   - Complete the transfer

2. **Conference Calls**:
   - Make call to test2
   - Put on hold
   - Call test3
   - Merge calls into conference

3. **Call History**:
   - View **History** tab
   - See call logs with duration
   - Redial from history

## 🔍 Monitoring and Debugging with Linphone

### Linphone's Built-in Debugging

#### Enable Verbose Logging
1. Go to **Linphone** → **Preferences**
2. Select **Advanced** → **Logs**
3. Set **Log Level** to **Debug** or **Trace**
4. Enable **Log to file**
5. Note the log file location (usually `~/Library/Application Support/Linphone/`)

#### Network Diagnostics
1. **Connection Test**:
   - Go to **Preferences** → **Network** → **SIP Accounts**
   - Select your account and click **Test**
   - Check registration status

2. **Audio Codec Information**:
   - Go to **Preferences** → **Audio**
   - View **Codec List** to see available codecs
   - Enable/disable specific codecs for testing

3. **Network Settings**:
   - **Preferences** → **Network** → **NAT and Firewall**
   - Set **Firewall policy** to "Use direct connection"
   - Disable ICE for local testing

### Server-side Monitoring

```bash
# SIP registration and calls
docker compose logs -f sip-server | grep -E "REGISTER|INVITE|BYE"

# All SIP traffic with details
docker compose exec sip-server tcpdump -i any -n port 5060 -A -s 0

# Detailed Kamailio logs
docker compose exec sip-server tail -f /var/log/kamailio/kamailio.log

# Monitor specific user registration
docker compose logs -f sip-server | grep "test1\|test2"
```

### Check Registration Status

```bash
# See registered users
docker compose exec sip-server kamctl ul show

# Check specific user
docker compose exec sip-server kamctl ul show test1
```

### Monitor Active Calls

```bash
# First, get admin token
ADMIN_TOKEN=$(docker compose exec sip-server python -c "
from src.utils.auth import create_access_token
from datetime import timedelta
token = create_access_token(data={'sub': 'admin', 'role': 'admin'}, expires_delta=timedelta(days=1))
print(token)
" 2>/dev/null | tr -d '\r')

# Get active calls
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8080/api/calls/active | jq

# Get user statistics
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8080/api/sip-users/1/stats | jq
```

## 🧪 Comprehensive Testing with Linphone

### 1. Registration Testing
```bash
# Monitor registration process
docker compose logs -f sip-server | grep -E "REGISTER|200 OK|401"

# In Linphone: Go to account, click "Register"
# Watch server logs for registration flow
```

### 2. Basic Call Flow Testing
1. **Start monitoring**:
   ```bash
   # Terminal 1: Monitor call flow
   docker compose logs -f sip-server | grep -E "call_id|INVITE|200 OK|ACK|BYE"
   
   # Terminal 2: Monitor RTP
   sudo tcpdump -i any -n "udp and portrange 10000-10100"
   ```

2. **In Linphone**: Make call from test1 to test2
3. **Watch logs**: Verify complete SIP call flow

### 3. Linphone Feature Testing

#### DTMF Testing
1. **During active call**: Use Linphone dial pad
2. **Monitor DTMF**: 
   ```bash
   docker compose logs -f sip-server | grep -i "dtmf\|info"
   ```
3. **Verify AI receives DTMF** (if AI platform connected)

#### Hold/Resume Testing
1. **Hold call**: Click hold button in Linphone
2. **Check status**: Call should show "On hold"
3. **Resume**: Click resume button
4. **Monitor**: Watch for INVITE/re-INVITE messages

#### Transfer Testing
1. **During call**: Click **Transfer** in Linphone
2. **Enter target**: `test3@localhost`
3. **Complete transfer**: Follow Linphone prompts
4. **Verify**: test2 should be connected to test3

#### Conference Testing
1. **Call test2**: Establish first call
2. **Add participant**: Click "Add call" → call test3
3. **Merge calls**: Click "Conference"
4. **Verify audio**: All parties should hear each other

### 4. Error Scenario Testing

#### Invalid User Testing
```bash
# In Linphone: Try calling test99@localhost
# Expected: 404 Not Found

# Monitor logs
docker compose logs -f sip-server | grep "404"
```

#### Wrong Password Testing
1. **Change password** in Linphone account settings
2. **Try to register**: Should fail with 401
3. **Check logs**:
   ```bash
   docker compose logs -f sip-server | grep "401\|authentication"
   ```

#### Concurrent Call Limit Testing
1. **Set low limit**: Update test user to max 1 call
2. **Make first call**: Should succeed
3. **Make second call**: Should be rejected
4. **Check API**:
   ```bash
   curl -H "Authorization: Bearer $ADMIN_TOKEN" \
        http://localhost:8080/api/calls/active
   ```

### 5. Codec Testing

#### Test Different Codecs
1. **Linphone Codec Settings**:
   - **Preferences** → **Audio** → **Codecs**
   - Enable only PCMU → Test call
   - Enable only PCMA → Test call
   - Enable G722 → Test call (if supported)

2. **Monitor codec negotiation**:
   ```bash
   docker compose logs -f sip-server | grep -i "codec\|sdp"
   ```

### 6. AI Platform Integration Testing

If AI platform is configured:

#### Full AI Call Flow
1. **Start AI platform monitoring**:
   ```bash
   # Monitor WebSocket connections
   docker compose logs -f sip-server | grep -E "websocket|ai_platform"
   ```

2. **Make call to AI-enabled number**:
   - Call should connect to AI platform
   - Speak and verify AI responses
   - Test DTMF interaction with AI

3. **Audio quality testing**:
   - Verify 8kHz → 16kHz resampling
   - Check for audio delays
   - Test audio clarity

#### AI Platform Connection Test
```bash
# Test WebSocket connection
docker compose exec sip-server python -c "
import asyncio
import websockets
import json

async def test_ai_connection():
    try:
        uri = 'ws://host.docker.internal:8001/ws/voice'
        async with websockets.connect(uri) as websocket:
            # Send test message
            test_msg = {
                'type': 'test',
                'call_id': 'test-123',
                'data': 'Hello AI Platform'
            }
            await websocket.send(json.dumps(test_msg))
            response = await websocket.recv()
            print(f'✅ AI Platform response: {response}')
    except Exception as e:
        print(f'❌ AI Platform connection failed: {e}')

asyncio.run(test_ai_connection())
"
```

## 🛠️ Troubleshooting with Linphone

### Linphone Registration Issues

#### Check Linphone Status
1. **Account Status**:
   - In Linphone, check account dropdown
   - Should show green dot for registered accounts
   - Red dot indicates registration failure

2. **Registration Details**:
   - Go to **Preferences** → **Network** → **SIP Accounts**
   - Select account and view **Status**
   - Check error messages

3. **Linphone Log Analysis**:
   ```bash
   # View Linphone logs
   tail -f ~/Library/Application\ Support/Linphone/linphone.log
   
   # Look for registration errors
   grep -i "register\|401\|403" ~/Library/Application\ Support/Linphone/linphone.log
   ```

#### Server-side Verification
```bash
# Check if SIP server is running
docker compose ps
curl http://localhost:8080/health

# Verify test users exist
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8080/api/sip-users/

# Check Kamailio is listening
netstat -an | grep 5060
```

### Audio Issues with Linphone

#### Codec Configuration
1. **Check Available Codecs**:
   - **Preferences** → **Audio** → **Codecs**
   - Ensure PCMU and PCMA are enabled
   - For testing, disable other codecs temporarily

2. **Audio Device Settings**:
   - **Preferences** → **Audio** → **Playback device**
   - **Preferences** → **Audio** → **Capture device**
   - Test microphone and speakers

3. **RTP Debugging**:
   ```bash
   # Check RTP ports are working
   docker compose exec sip-server netstat -ulnp | grep rtpproxy
   
   # Monitor RTP traffic during call
   sudo tcpdump -i any -n "udp and portrange 10000-10100"
   ```

#### Linphone Audio Diagnostics
1. **Audio Wizard**:
   - Go to **Preferences** → **Audio**
   - Click **Audio setup wizard**
   - Test microphone and speakers

2. **Echo Cancellation**:
   - Enable **Echo cancellation** in Audio preferences
   - Adjust **Microphone gain** if needed

### Call Connection Issues

#### Linphone Call Debugging
1. **Check Call Status**:
   - During call attempt, watch status messages
   - Note any error codes (404, 486, 503, etc.)

2. **SIP Headers Analysis**:
   - Enable debug logging in Linphone
   - Check logs for SIP INVITE/response messages

3. **Network Connectivity**:
   ```bash
   # Test connectivity to SIP server
   telnet localhost 5060
   
   # Check if port is accessible
   nc -u localhost 5060  # UDP test
   nc localhost 5060     # TCP test
   ```

#### Common Error Codes
- **404 Not Found**: User doesn't exist - check username
- **401 Unauthorized**: Wrong password - verify credentials
- **486 Busy Here**: User busy or max calls reached
- **503 Service Unavailable**: Server overloaded or down

### AI Platform Integration Testing

If you have AI platform configured:

```bash
# Verify AI platform connection
docker compose exec sip-server python -c "
import asyncio
import websockets
async def test():
    try:
        async with websockets.connect('ws://host.docker.internal:8001/ws/voice'):
            print('✅ WebSocket connection successful')
    except Exception as e:
        print(f'❌ WebSocket connection failed: {e}')
asyncio.run(test())
"

# Monitor AI integration during calls
docker compose logs -f sip-server | grep -E "websocket|ai_platform"
```

### Performance Issues

#### Linphone Performance Tuning
1. **Disable Video**:
   - **Preferences** → **Video** → Uncheck **Enable video**
   - Reduces CPU usage for audio-only testing

2. **Network Optimization**:
   - **Preferences** → **Network** → **Quality of service**
   - Enable **Enable adaptive rate control**
   - Set appropriate bandwidth limits

3. **Audio Quality**:
   - Lower audio quality for testing: 8kHz, mono
   - Higher quality for production: 16kHz, stereo

## 📊 Performance Testing

### Simple Load Test

```bash
# Create multiple users
for i in {1..20}; do
  curl -s -X POST http://localhost:8080/api/sip-users/ \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d "{
      \"username\": \"load$i\",
      \"password\": \"pass$i\",
      \"display_name\": \"Load Test User $i\"
    }"
done

# Monitor resource usage
docker stats sip-server
```

## 🎯 Next Steps

Once local testing is working well:

1. **Test with real phones**: Use SIP apps on mobile devices
2. **Add external connectivity**: Configure port forwarding or VPN
3. **Integrate wholesale provider**: Add Skyetel or similar for real numbers
4. **Deploy to production**: Use Kubernetes deployment guide

## 💡 Tips for Effective Testing

1. **Use different SIP clients** to ensure compatibility
2. **Test edge cases**: Wrong passwords, non-existent users, network issues
3. **Monitor logs continuously** during testing
4. **Test with actual AI platform** when possible
5. **Document any issues** for troubleshooting

## 🔧 Linphone Testing Commands Reference

### Service Management
```bash
# Start/Stop SIP Server
docker compose up -d                    # Start all services
docker compose down                     # Stop services
docker compose restart sip-server       # Restart SIP server
docker compose logs -f sip-server       # View real-time logs

# Service Health Checks
curl http://localhost:8080/health        # API health check
curl http://localhost:8080/metrics       # Prometheus metrics
docker compose ps                       # Check service status
```

### User Management
```bash
# Test User Setup
./setup_test_users.sh                   # Create test users
kamctl ul show                          # Show registered users
kamctl ul show test1                    # Show specific user

# User Management via API
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8080/api/sip-users/    # List all users

curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8080/api/sip-users/1/stats  # User statistics
```

### Linphone-Specific Debugging
```bash
# Linphone Logs
tail -f ~/Library/Application\ Support/Linphone/linphone.log
grep -i "register\|invite" ~/Library/Application\ Support/Linphone/linphone.log

# Network Testing
telnet localhost 5060                    # Test SIP port
nc -u localhost 5060                    # Test UDP connectivity
ipconfig getifaddr en0                  # Get Mac IP for mobile testing
```

### SIP Traffic Monitoring
```bash
# SIP Signaling
docker compose logs -f sip-server | grep -E "REGISTER|INVITE|BYE|200 OK"
tcpdump -i any -n port 5060 -A          # Capture SIP packets

# RTP Media Traffic
sudo tcpdump -i any -n "udp and portrange 10000-10100"
docker compose exec sip-server netstat -ulnp | grep rtpproxy

# Specific User Activity
docker compose logs -f sip-server | grep "test1\|test2"
```

### Call Testing Commands
```bash
# Monitor active calls
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8080/api/calls/active

# Check call statistics
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8080/api/sip-users/1/calls

# Test DTMF detection
docker compose logs -f sip-server | grep -i "dtmf\|info"
```

### AI Platform Testing
```bash
# Test WebSocket connection
docker compose exec sip-server python -c "
import asyncio, websockets
asyncio.run(websockets.connect('ws://host.docker.internal:8001/ws/voice'))
print('WebSocket OK')
"

# Monitor AI integration
docker compose logs -f sip-server | grep -E "websocket|ai_platform|resampl"
```

### Quick Troubleshooting
```bash
# Check everything is working
docker compose ps && curl -s http://localhost:8080/health && echo "✅ Server OK"

# Reset everything
docker compose down && docker compose up -d && sleep 10 && ./setup_test_users.sh

# Access container for debugging
docker compose exec sip-server bash
```

## 📱 Linphone Quick Setup Checklist

- [ ] Download and install Linphone from linphone.org
- [ ] Run `./setup_test_users.sh` to create test accounts
- [ ] Configure test1 account in Linphone (localhost, UDP)
- [ ] Verify green registration status
- [ ] Configure test2 account (second device or account switching)
- [ ] Test call between test1 and test2
- [ ] Verify audio quality and features (hold, DTMF, transfer)
- [ ] Enable debug logging for troubleshooting
- [ ] Test error scenarios (wrong password, invalid user)
- [ ] Monitor server logs during all testing

## 📚 Linphone Documentation

- [Linphone User Guide](https://wiki.linphone.org/xwiki/wiki/public/view/Linphone/User%20Guide/)
- [Linphone FAQ](https://wiki.linphone.org/xwiki/wiki/public/view/Linphone/FAQ/)
- [SIP Account Configuration](https://wiki.linphone.org/xwiki/wiki/public/view/Linphone/How%20to%20configure%20a%20SIP%20account/)
- [Troubleshooting Guide](https://wiki.linphone.org/xwiki/wiki/public/view/Linphone/Troubleshooting/)
- [Audio Configuration](https://wiki.linphone.org/xwiki/wiki/public/view/Linphone/Audio%20Configuration/)

## 🎯 Next Steps After Local Testing

1. **Mobile Testing**: Install Linphone on iOS/Android for multi-device testing
2. **Network Testing**: Test from different networks (WiFi, cellular)
3. **Load Testing**: Create multiple test users and simulate concurrent calls
4. **AI Integration**: Connect your AI platform and test voice conversations
5. **Production Setup**: Deploy to cloud with real phone numbers and external access

Happy testing with Linphone! 🎉
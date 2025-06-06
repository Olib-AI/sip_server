# SIP User Authentication System

## Overview

The SIP server now includes a comprehensive user authentication system that provides secure username/password authentication for SIP clients. This system is designed to work with internal platforms and external SIP clients, offering full CRUD operations for user management and secure authentication for all SIP communications.

## Architecture

### Components

1. **SIP User Database Models** - Complete user management with HA1 hash storage
2. **SIP Authentication API** - CRUD operations for user management
3. **Kamailio Integration** - Real-time authentication with the SIP server
4. **Separate JWT Security** - Dedicated secret for SIP user management API
5. **Call Session Tracking** - Monitor active calls and enforce limits

### Security Features

- **HA1 Hash Authentication** - Industry-standard SIP digest authentication
- **Account Lockout** - Protection against brute force attacks
- **Concurrent Call Limits** - Per-user call restrictions
- **Admin-Only Management** - Secure API access with admin privileges
- **Separate JWT Secret** - Isolated security for SIP user management

## Database Schema

### SIP Users Table (`sip_users`)

```sql
CREATE TABLE sip_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200),
    password VARCHAR(255) NOT NULL,  -- Plain password for HA1 generation
    ha1 VARCHAR(32) NOT NULL,        -- MD5(username:realm:password)
    realm VARCHAR(100) NOT NULL DEFAULT 'sip.olib.ai',
    is_active BOOLEAN DEFAULT TRUE,
    is_blocked BOOLEAN DEFAULT FALSE,
    max_concurrent_calls INTEGER DEFAULT 3,
    call_recording_enabled BOOLEAN DEFAULT TRUE,
    sms_enabled BOOLEAN DEFAULT TRUE,
    
    -- Foreign key to API user (optional)
    api_user_id INTEGER REFERENCES api_users(id),
    
    -- SIP-specific metadata
    contact_info JSONB,
    user_agent VARCHAR(200),
    last_registration TIMESTAMP WITH TIME ZONE,
    registration_expires TIMESTAMP WITH TIME ZONE,
    failed_auth_attempts INTEGER DEFAULT 0,
    account_locked_until TIMESTAMP WITH TIME ZONE,
    
    -- Usage statistics
    total_calls INTEGER DEFAULT 0,
    total_minutes INTEGER DEFAULT 0,
    total_sms INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE
);
```

### Kamailio Subscriber Table (`subscriber`)

```sql
CREATE TABLE subscriber (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    domain VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL,  -- HA1 hash
    ha1 VARCHAR(32) NOT NULL,        -- MD5(username:realm:password)
    ha1b VARCHAR(32) DEFAULT '',     -- MD5(username@domain:realm:password)
    datetime_created INTEGER DEFAULT 0,
    datetime_modified INTEGER DEFAULT 0
);
```

### Call Session Tracking (`sip_call_sessions`)

```sql
CREATE TABLE sip_call_sessions (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(255) UNIQUE NOT NULL,
    sip_user_id INTEGER REFERENCES sip_users(id) NOT NULL,
    from_uri VARCHAR(255) NOT NULL,
    to_uri VARCHAR(255) NOT NULL,
    contact_uri VARCHAR(255),
    call_direction VARCHAR(10) NOT NULL,  -- inbound/outbound
    call_state VARCHAR(20) NOT NULL,      -- ringing/connected/held/ended
    media_session_id VARCHAR(255),
    
    -- Call timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    answer_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    
    -- Call metadata
    sip_headers JSONB,
    codec_used VARCHAR(20),
    ai_conversation_id VARCHAR(255),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## API Endpoints

### Authentication

All SIP user management endpoints require admin authentication:

```bash
# Headers required for all requests
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json
```

### SIP User Management

#### Create SIP User

```bash
POST /api/sip-users/
Content-Type: application/json

{
    "username": "user123",
    "password": "secure_password",
    "display_name": "John Doe",
    "realm": "sip.olib.ai",
    "max_concurrent_calls": 3,
    "call_recording_enabled": true,
    "sms_enabled": true,
    "api_user_id": 1  // Optional link to API user
}
```

**Response:**
```json
{
    "id": 1,
    "username": "user123",
    "display_name": "John Doe",
    "realm": "sip.olib.ai",
    "is_active": true,
    "is_blocked": false,
    "max_concurrent_calls": 3,
    "call_recording_enabled": true,
    "sms_enabled": true,
    "total_calls": 0,
    "total_minutes": 0,
    "total_sms": 0,
    "failed_auth_attempts": 0,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
}
```

#### List SIP Users

```bash
GET /api/sip-users/?page=1&per_page=50&active_only=false&search=john

# Response
{
    "users": [...],
    "total": 100,
    "page": 1,
    "per_page": 50
}
```

#### Get SIP User

```bash
GET /api/sip-users/{user_id}
```

#### Update SIP User

```bash
PUT /api/sip-users/{user_id}
Content-Type: application/json

{
    "password": "new_secure_password",  // Optional
    "display_name": "John Smith",
    "is_active": true,
    "is_blocked": false,
    "max_concurrent_calls": 5
}
```

#### Delete SIP User

```bash
DELETE /api/sip-users/{user_id}
# Returns: 204 No Content
```

#### Unlock SIP User

```bash
POST /api/sip-users/{user_id}/unlock
# Resets failed auth attempts and removes account lock
```

#### Get SIP User Credentials

```bash
GET /api/sip-users/{user_id}/credentials

# Response
{
    "username": "user123",
    "realm": "sip.olib.ai",
    "sip_domain": "sip.olib.ai",
    "proxy_address": "sip.olib.ai",
    "proxy_port": 5060,
    "registration_expires": 3600,
    "max_concurrent_calls": 3
}
```

#### Get User Call History

```bash
GET /api/sip-users/{user_id}/calls?active_only=false&limit=50
```

#### Get User Statistics

```bash
GET /api/sip-users/{user_id}/stats

# Response
{
    "username": "user123",
    "total_calls": 45,
    "total_minutes": 1234,
    "total_sms": 67,
    "active_calls": 2,
    "failed_auth_attempts": 0,
    "last_seen": "2024-01-01T12:00:00Z",
    "registration_status": "registered"
}
```

#### Bulk Create Users

```bash
POST /api/sip-users/bulk-create
Content-Type: application/json

[
    {
        "username": "user1",
        "password": "password1",
        "display_name": "User One"
    },
    {
        "username": "user2", 
        "password": "password2",
        "display_name": "User Two"
    }
]
```

### SIP Authentication Endpoints (For Kamailio)

#### Authenticate SIP Request

```bash
POST /api/sip-auth/authenticate
Content-Type: application/json

{
    "username": "user123",
    "realm": "sip.olib.ai",
    "method": "REGISTER",
    "uri": "sip:sip.olib.ai",
    "nonce": "1234567890abcdef",
    "response": "calculated_md5_response",
    "algorithm": "MD5"
}
```

**Response:**
```json
{
    "authenticated": true,
    "user_id": 1,
    "username": "user123",
    "reason": null,
    "account_locked": false,
    "account_inactive": false
}
```

#### Get User Info for Kamailio

```bash
GET /api/sip-auth/user/{username}/info?realm=sip.olib.ai

# Response includes authorization info for call routing
{
    "username": "user123",
    "realm": "sip.olib.ai",
    "is_active": true,
    "is_blocked": false,
    "max_concurrent_calls": 3,
    "active_calls": 1,
    "can_make_call": true,
    "call_recording_enabled": true,
    "sms_enabled": true
}
```

#### Start Call Session

```bash
POST /api/sip-auth/call-session/start
Content-Type: application/json

{
    "call_id": "unique-call-id-123",
    "username": "user123",
    "realm": "sip.olib.ai",
    "from_uri": "sip:user123@sip.olib.ai",
    "to_uri": "sip:+1234567890@sip.olib.ai",
    "direction": "outbound",
    "headers": {
        "User-Agent": "SIP Client 1.0"
    }
}
```

#### Update Call Session State

```bash
PUT /api/sip-auth/call-session/{call_id}/state
Content-Type: application/json

{
    "state": "connected",  // ringing/connected/held/ended
    "codec": "PCMU",
    "media_session_id": "rtp-session-456"
}
```

#### Update Registration

```bash
POST /api/sip-auth/registration
Content-Type: application/json

{
    "username": "user123",
    "realm": "sip.olib.ai",
    "contact": "sip:user123@192.168.1.100:5060",
    "expires": 3600,
    "user_agent": "Linphone/4.2.0"
}
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# SIP User Management JWT (separate secret for higher security)
SIP_JWT_SECRET=your-sip-user-management-secret-256-bit-key-change-this

# SIP Domain Configuration
SIP_DOMAIN=sip.olib.ai
SIP_PROXY_ADDRESS=sip.olib.ai
SIP_PROXY_PORT=5060
```

### Kamailio Configuration

The Kamailio configuration has been updated to integrate with the SIP user authentication system:

```kamailio
# Authentication module configuration
modparam("auth_db", "calculate_ha1", 0)  # HA1 is pre-calculated
modparam("auth_db", "password_column", "ha1")  # Use HA1 hash column
modparam("auth_db", "user_column", "username")
modparam("auth_db", "domain_column", "domain")
modparam("auth_db", "table", "subscriber")

# HTTP client for API integration
loadmodule "http_client.so"
modparam("http_client", "httpcon", "api=>http://127.0.0.1:8000")
```

## Client Configuration

### SIP Client Setup

Configure SIP clients with these parameters:

```
Username: user123
Password: secure_password
Realm: sip.olib.ai
Proxy: sip.olib.ai:5060
Register: yes
Registration Expires: 3600 seconds
Transport: UDP/TCP
```

### Example SIP Client Configuration (Linphone)

```ini
[proxy_0]
reg_proxy=sip.olib.ai
reg_identity=sip:user123@sip.olib.ai
reg_expires=3600
reg_sendregister=1
realm=sip.olib.ai
quality_reporting_enabled=0
publish_enabled=0
dial_escape_plus=0
```

## Security Features

### Account Protection

- **Maximum 5 failed auth attempts** before account lockout
- **30-minute lockout duration** (configurable)
- **Automatic unlock** after lockout period expires
- **Manual unlock** via admin API

### Call Restrictions

- **Per-user concurrent call limits** (default: 3)
- **Active call tracking** with real-time monitoring
- **Call recording controls** per user
- **SMS enable/disable** per user

### Authentication Security

- **HA1 hash storage** - passwords never stored in plain text
- **Digest authentication** - industry standard SIP security
- **Separate JWT secrets** - isolated security for user management
- **Admin-only access** - user management requires admin privileges

## Usage Examples

### Creating Users for Internal Platform

```python
import requests

# Create SIP user for platform integration
user_data = {
    "username": "platform_user_001",
    "password": "secure_random_password", 
    "display_name": "Platform User 001",
    "realm": "sip.olib.ai",
    "max_concurrent_calls": 5,
    "call_recording_enabled": True,
    "sms_enabled": True,
    "api_user_id": 123  # Link to existing API user
}

response = requests.post(
    "https://your-sip-server.com/api/sip-users/",
    json=user_data,
    headers={
        "Authorization": "Bearer your-admin-jwt-token",
        "Content-Type": "application/json"
    }
)

if response.status_code == 201:
    sip_user = response.json()
    print(f"Created SIP user: {sip_user['username']}")
```

### Bulk User Creation

```python
# Create multiple users at once
users = []
for i in range(100):
    users.append({
        "username": f"user_{i:03d}",
        "password": f"secure_password_{i}",
        "display_name": f"User {i:03d}",
        "realm": "sip.olib.ai"
    })

response = requests.post(
    "https://your-sip-server.com/api/sip-users/bulk-create",
    json=users,
    headers={
        "Authorization": "Bearer your-admin-jwt-token",
        "Content-Type": "application/json"
    }
)

created_users = response.json()
print(f"Created {len(created_users)} users")
```

### Managing User Status

```python
# Block a user
requests.put(
    f"https://your-sip-server.com/api/sip-users/{user_id}",
    json={"is_blocked": True},
    headers={"Authorization": "Bearer your-admin-jwt-token"}
)

# Unlock a locked account
requests.post(
    f"https://your-sip-server.com/api/sip-users/{user_id}/unlock",
    headers={"Authorization": "Bearer your-admin-jwt-token"}
)

# Get user statistics
stats = requests.get(
    f"https://your-sip-server.com/api/sip-users/{user_id}/stats",
    headers={"Authorization": "Bearer your-admin-jwt-token"}
).json()

print(f"User has made {stats['total_calls']} calls")
```

## Testing

### Unit Tests

```bash
# Run SIP authentication tests
python -m pytest src/tests/unit/test_sip_authentication.py -v

# Run SIP user API tests  
python -m pytest src/tests/integration/test_sip_user_api.py -v
```

### Manual Testing

```bash
# Test user creation
curl -X POST http://localhost:8080/api/sip-users/ \
  -H "Authorization: Bearer admin-token" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpass123",
    "display_name": "Test User"
  }'

# Test authentication
curl -X POST http://localhost:8080/api/sip-auth/authenticate \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "realm": "sip.olib.ai",
    "method": "REGISTER",
    "uri": "sip:sip.olib.ai",
    "nonce": "test_nonce",
    "response": "calculated_response_hash"
  }'
```

## Troubleshooting

### Common Issues

**Authentication Failures:**
- Check username and realm are correct
- Verify HA1 hash calculation
- Ensure user account is active and not blocked
- Check for account lockout status

**Registration Issues:**
- Verify SIP client configuration
- Check network connectivity to SIP proxy
- Ensure credentials are properly configured
- Check Kamailio logs for authentication errors

**Call Failures:**
- Verify user hasn't exceeded concurrent call limit
- Check if user account allows calls
- Verify call recording and SMS permissions
- Monitor call session tracking

### Debug Commands

```bash
# Check user status
curl -H "Authorization: Bearer admin-token" \
  http://localhost:8080/api/sip-users/1

# Get user statistics
curl -H "Authorization: Bearer admin-token" \
  http://localhost:8080/api/sip-users/1/stats

# Check active calls
curl -H "Authorization: Bearer admin-token" \
  http://localhost:8080/api/sip-users/1/calls?active_only=true

# Unlock account
curl -X POST -H "Authorization: Bearer admin-token" \
  http://localhost:8080/api/sip-users/1/unlock
```

### Logs

Monitor these log sources:

```bash
# SIP server API logs
docker-compose logs -f sip-server | grep "sip_auth"

# Kamailio authentication logs  
docker-compose logs -f sip-server | grep "Auth"

# Database query logs
docker-compose logs -f postgres | grep "subscriber"
```

## Production Deployment

### Security Checklist

- ✅ Generate secure SIP_JWT_SECRET (256-bit minimum)
- ✅ Use strong passwords for SIP users (8+ characters)
- ✅ Enable TLS for SIP signaling
- ✅ Configure appropriate concurrent call limits
- ✅ Set up proper firewall rules for SIP ports
- ✅ Monitor failed authentication attempts
- ✅ Regular backup of user database
- ✅ Implement log rotation and monitoring

### Performance Tuning

- **Database indexes** - Already optimized for authentication queries
- **Connection pooling** - Configure appropriate database connections
- **Kamailio memory** - Increase shared memory for large user bases
- **Call session cleanup** - Monitor and clean old call sessions
- **API rate limiting** - Protect against API abuse

### Monitoring

Set up monitoring for:

- Authentication success/failure rates
- Active user registrations
- Concurrent call counts per user
- Account lockout incidents
- API endpoint performance
- Database query performance

The SIP user authentication system is now production-ready and provides secure, scalable user management for your SIP infrastructure.
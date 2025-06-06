"""Pydantic schemas for API models."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum


class CallStatus(str, Enum):
    """Call status enumeration."""
    CONNECTING = "connecting"
    RINGING = "ringing"
    CONNECTED = "connected"
    ON_HOLD = "on_hold"
    ENDED = "ended"
    FAILED = "failed"


class SMSStatus(str, Enum):
    """SMS status enumeration."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class CallInitiate(BaseModel):
    """Schema for initiating a call."""
    from_number: str = Field(..., description="Caller phone number")
    to_number: str = Field(..., description="Callee phone number")
    headers: Optional[Dict[str, str]] = Field(default={}, description="Custom SIP headers")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for call events")
    timeout: Optional[int] = Field(60, description="Call timeout in seconds")
    
    @field_validator('from_number', 'to_number')
    @classmethod
    def validate_phone_number(cls, v):
        # Basic phone number validation
        if not v or len(v) < 10:
            raise ValueError('Invalid phone number')
        return v


class CallInfo(BaseModel):
    """Schema for call information."""
    call_id: str
    from_number: str
    to_number: str
    status: CallStatus
    direction: str = Field(..., pattern="^(inbound|outbound)$")
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[int] = None
    recording_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


class CallTransfer(BaseModel):
    """Schema for call transfer."""
    target_number: str = Field(..., description="Number to transfer to")
    blind_transfer: bool = Field(True, description="Blind transfer (no confirmation)")


class SMSSend(BaseModel):
    """Schema for sending SMS."""
    from_number: str = Field(..., description="Sender phone number")
    to_number: str = Field(..., description="Recipient phone number")
    message: str = Field(..., max_length=1600, description="SMS message content")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for SMS events")


class SMSInfo(BaseModel):
    """Schema for SMS information."""
    message_id: str
    from_number: str
    to_number: str
    message: str
    status: SMSStatus
    direction: str = Field(..., pattern="^(inbound|outbound)$")
    timestamp: datetime
    error: Optional[str] = None
    segments: int = Field(1, description="Number of SMS segments")


class BlockedNumber(BaseModel):
    """Schema for blocked number."""
    number: str = Field(..., description="Phone number to block")
    reason: Optional[str] = Field(None, description="Reason for blocking")
    blocked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="When the block expires")
    blocked_by: Optional[str] = None


class NumberInfo(BaseModel):
    """Schema for number information."""
    number: str
    display_name: Optional[str] = None
    registered: bool = False
    registration_time: Optional[datetime] = None
    capabilities: List[str] = Field(default=["voice", "sms"])
    metadata: Optional[Dict[str, Any]] = {}


class SIPConfig(BaseModel):
    """Schema for SIP configuration."""
    sip_domains: List[str] = Field(default=["sip.olib.ai"])
    rtp_port_start: int = Field(10000, ge=1024, le=65535)
    rtp_port_end: int = Field(20000, ge=1024, le=65535)
    max_concurrent_calls: int = Field(1000, ge=1)
    call_timeout: int = Field(3600, ge=60, description="Max call duration in seconds")
    enable_recording: bool = False
    enable_transcription: bool = False
    nat_traversal: bool = True
    tls_enabled: bool = True
    auto_reload: bool = False
    rate_limit: Dict[str, int] = Field(default={
        "calls_per_minute": 60,
        "sms_per_minute": 100
    })


class ServerStatus(BaseModel):
    """Schema for server status."""
    status: str = Field(..., pattern="^(healthy|degraded|unhealthy)$")
    uptime: int = Field(..., description="Uptime in seconds")
    active_calls: int = 0
    total_calls_today: int = 0
    registered_numbers: int = 0
    memory_usage: float = Field(..., description="Memory usage percentage")
    cpu_usage: float = Field(..., description="CPU usage percentage")
    last_error: Optional[str] = None
    version: str


class CallWebhook(BaseModel):
    """Schema for call webhook data."""
    call_id: str
    from_number: str
    to_number: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    headers: Optional[Dict[str, str]] = {}
    metadata: Optional[Dict[str, Any]] = {}


class SMSWebhook(BaseModel):
    """Schema for SMS webhook data."""
    message_id: str
    from_number: str
    to_number: str
    message: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    forward_url: Optional[str] = None


class RegistrationWebhook(BaseModel):
    """Schema for registration webhook data."""
    user: str
    domain: str
    contact: str
    expires: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# SIP User Management Schemas

class SIPUserCreate(BaseModel):
    """Schema for creating a SIP user."""
    username: str = Field(..., min_length=3, max_length=100, description="SIP username")
    password: str = Field(..., min_length=8, max_length=255, description="SIP password")
    display_name: Optional[str] = Field(None, max_length=200, description="Display name")
    realm: str = Field("sip.olib.ai", description="SIP realm/domain")
    max_concurrent_calls: int = Field(3, ge=1, le=10, description="Max concurrent calls")
    call_recording_enabled: bool = Field(True, description="Enable call recording")
    sms_enabled: bool = Field(True, description="Enable SMS")
    api_user_id: Optional[int] = Field(None, description="Associated API user ID")
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v.lower()
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class SIPUserUpdate(BaseModel):
    """Schema for updating a SIP user."""
    password: Optional[str] = Field(None, min_length=8, max_length=255)
    display_name: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None
    is_blocked: Optional[bool] = None
    max_concurrent_calls: Optional[int] = Field(None, ge=1, le=10)
    call_recording_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if v is not None and len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class SIPUserInfo(BaseModel):
    """Schema for SIP user information."""
    id: int
    username: str
    display_name: Optional[str]
    realm: str
    is_active: bool
    is_blocked: bool
    max_concurrent_calls: int
    call_recording_enabled: bool
    sms_enabled: bool
    api_user_id: Optional[int]
    
    # Statistics
    total_calls: int
    total_minutes: int
    total_sms: int
    failed_auth_attempts: int
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    last_seen: Optional[datetime]
    last_registration: Optional[datetime]
    registration_expires: Optional[datetime]
    account_locked_until: Optional[datetime]
    
    # SIP metadata
    contact_info: Optional[Dict[str, Any]]
    user_agent: Optional[str]
    
    class Config:
        from_attributes = True


class SIPUserList(BaseModel):
    """Schema for SIP user list response."""
    users: List[SIPUserInfo]
    total: int
    page: int
    per_page: int


class SIPUserCredentials(BaseModel):
    """Schema for SIP user credentials response (for client configuration)."""
    username: str
    realm: str
    sip_domain: str
    proxy_address: str
    proxy_port: int
    registration_expires: int
    max_concurrent_calls: int
    
    class Config:
        from_attributes = True


class SIPCallSessionInfo(BaseModel):
    """Schema for SIP call session information."""
    id: int
    call_id: str
    sip_user_id: int
    sip_username: str
    from_uri: str
    to_uri: str
    contact_uri: Optional[str]
    call_direction: str
    call_state: str
    media_session_id: Optional[str]
    codec_used: Optional[str]
    ai_conversation_id: Optional[str]
    
    # Call timing
    start_time: datetime
    answer_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_seconds: Optional[int] = None
    
    # Metadata
    sip_headers: Optional[Dict[str, Any]]
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class SIPUserStats(BaseModel):
    """Schema for SIP user statistics."""
    username: str
    total_calls: int
    total_minutes: int
    total_sms: int
    active_calls: int
    failed_auth_attempts: int
    last_seen: Optional[datetime]
    registration_status: str  # registered/expired/never
    
    class Config:
        from_attributes = True


class SIPAuthRequest(BaseModel):
    """Schema for SIP authentication request."""
    username: str
    realm: str
    method: str = "REGISTER"
    uri: str
    nonce: str
    response: str
    algorithm: str = "MD5"
    cnonce: Optional[str] = None
    nc: Optional[str] = None
    qop: Optional[str] = None


class SIPAuthResponse(BaseModel):
    """Schema for SIP authentication response."""
    authenticated: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    reason: Optional[str] = None
    account_locked: bool = False
    account_inactive: bool = False
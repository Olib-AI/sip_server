"""Pydantic schemas for API models."""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
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
    
    @validator('from_number', 'to_number')
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
    direction: str = Field(..., regex="^(inbound|outbound)$")
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
    direction: str = Field(..., regex="^(inbound|outbound)$")
    timestamp: datetime
    error: Optional[str] = None
    segments: int = Field(1, description="Number of SMS segments")


class BlockedNumber(BaseModel):
    """Schema for blocked number."""
    number: str = Field(..., description="Phone number to block")
    reason: Optional[str] = Field(None, description="Reason for blocking")
    blocked_at: datetime = Field(default_factory=datetime.utcnow)
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
    status: str = Field(..., regex="^(healthy|degraded|unhealthy)$")
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
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    headers: Optional[Dict[str, str]] = {}
    metadata: Optional[Dict[str, Any]] = {}


class SMSWebhook(BaseModel):
    """Schema for SMS webhook data."""
    message_id: str
    from_number: str
    to_number: str
    message: str
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    forward_url: Optional[str] = None


class RegistrationWebhook(BaseModel):
    """Schema for registration webhook data."""
    user: str
    domain: str
    contact: str
    expires: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
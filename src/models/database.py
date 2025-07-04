"""Database models and connection management."""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, JSON, ForeignKey, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.pool import NullPool
from datetime import datetime, timezone
import os
from typing import Optional
from ..utils.config import get_config

# Get database configuration
config = get_config()
DATABASE_URL = config.database.url

# Create engine
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # Disable connection pooling for async compatibility
    echo=False
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class CallRecord(Base):
    """Call detail records."""
    __tablename__ = "call_records"
    
    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String(255), unique=True, index=True, nullable=False)
    from_number = Column(String(50), index=True, nullable=False)
    to_number = Column(String(50), index=True, nullable=False)
    direction = Column(String(10), nullable=False)  # inbound/outbound
    status = Column(String(20), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration = Column(Integer)  # seconds
    recording_url = Column(String(500))
    transcription = Column(JSON)
    call_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('idx_call_time', 'start_time', 'end_time'),
    )


class SMSRecord(Base):
    """SMS message records."""
    __tablename__ = "sms_records"
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), unique=True, index=True, nullable=False)
    from_number = Column(String(50), index=True, nullable=False)
    to_number = Column(String(50), index=True, nullable=False)
    direction = Column(String(10), nullable=False)  # inbound/outbound
    message = Column(String(1600), nullable=False)
    status = Column(String(20), nullable=False)
    segments = Column(Integer, default=1)
    error_message = Column(String(500))
    sms_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    delivered_at = Column(DateTime)


class RegisteredNumber(Base):
    """Registered phone numbers."""
    __tablename__ = "registered_numbers"
    
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100))
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    domain = Column(String(100), nullable=False)
    capabilities = Column(JSON, default=["voice", "sms"])
    active = Column(Boolean, default=True)
    sms_metadata = Column(JSON)
    registered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime)
    
    # Relationships
    blocked_numbers = relationship("BlockedNumber", back_populates="registered_number")


class BlockedNumber(Base):
    """Blocked phone numbers."""
    __tablename__ = "blocked_numbers"
    
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(50), unique=True, index=True, nullable=False)
    registered_number_id = Column(Integer, ForeignKey("registered_numbers.id"))
    reason = Column(String(500))
    blocked_by = Column(String(100))
    blocked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, index=True)
    
    # Relationships
    registered_number = relationship("RegisteredNumber", back_populates="blocked_numbers")


class Configuration(Base):
    """System configuration."""
    __tablename__ = "configuration"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(JSON, nullable=False)
    description = Column(String(500))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(String(100))


class WebhookLog(Base):
    """Webhook delivery logs."""
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), index=True, nullable=False)
    url = Column(String(500), nullable=False)
    payload = Column(JSON, nullable=False)
    response_status = Column(Integer)
    response_body = Column(String(1000))
    attempts = Column(Integer, default=1)
    success = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    delivered_at = Column(DateTime)


class SystemMetrics(Base):
    """System performance metrics."""
    __tablename__ = "system_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(50), index=True, nullable=False)
    value = Column(Float, nullable=False)
    sms_metadata = Column(JSON)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    __table_args__ = (
        Index('idx_metrics_time', 'metric_type', 'timestamp'),
    )


class APIUser(Base):
    """API users for authentication."""
    __tablename__ = "api_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(String(255), unique=True, index=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    sip_users = relationship("SIPUser", back_populates="api_user")


class SIPUser(Base):
    """SIP users for authentication with username/password credentials."""
    __tablename__ = "sip_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200))
    password = Column(String(255), nullable=False)  # Plain password for HA1 generation
    ha1 = Column(String(32), nullable=False)  # MD5(username:realm:password) for SIP auth
    realm = Column(String(100), nullable=False, default="sip.olib.ai")
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    max_concurrent_calls = Column(Integer, default=3)
    call_recording_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=True)
    
    # Foreign key to API user (internal platform management)
    api_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    
    # SIP-specific metadata
    contact_info = Column(JSON)  # SIP contact information
    user_agent = Column(String(200))  # Last seen User-Agent
    last_registration = Column(DateTime)
    registration_expires = Column(DateTime)
    failed_auth_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime)
    
    # Usage statistics
    total_calls = Column(Integer, default=0)
    total_minutes = Column(Integer, default=0)
    total_sms = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime)
    
    # Relationships
    api_user = relationship("APIUser", back_populates="sip_users")
    call_sessions = relationship("SIPCallSession", back_populates="sip_user")
    
    __table_args__ = (
        Index('idx_sip_user_auth', 'username', 'realm'),
        Index('idx_sip_user_active', 'is_active', 'is_blocked'),
    )


class SIPCallSession(Base):
    """Active SIP call sessions for tracking user calls."""
    __tablename__ = "sip_call_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String(255), unique=True, index=True, nullable=False)
    sip_user_id = Column(Integer, ForeignKey("sip_users.id"), nullable=False)
    from_uri = Column(String(255), nullable=False)
    to_uri = Column(String(255), nullable=False)
    contact_uri = Column(String(255))
    call_direction = Column(String(10), nullable=False)  # inbound/outbound
    call_state = Column(String(20), nullable=False)  # ringing/connected/held/ended
    media_session_id = Column(String(255))  # RTP session ID
    
    # Call timing
    start_time = Column(DateTime, nullable=False)
    answer_time = Column(DateTime)
    end_time = Column(DateTime)
    
    # Call metadata
    sip_headers = Column(JSON)
    codec_used = Column(String(20))
    ai_conversation_id = Column(String(255))
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    sip_user = relationship("SIPUser", back_populates="call_sessions")
    
    __table_args__ = (
        Index('idx_call_session_user', 'sip_user_id', 'call_state'),
        Index('idx_call_session_time', 'start_time', 'end_time'),
    )


class Subscriber(Base):
    """Kamailio subscriber table for SIP authentication compatibility."""
    __tablename__ = "subscriber"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, index=True, default="")
    domain = Column(String(64), nullable=False, default="")
    password = Column(String(25), nullable=False, default="")  # HA1 hash for SIP auth
    email_address = Column(String(64), nullable=False, default="")
    ha1 = Column(String(64), nullable=False, default="")  # MD5(username:realm:password)
    ha1b = Column(String(64), nullable=False, default="")  # MD5(username@domain:realm:password)
    rpid = Column(String(64), nullable=True)
    
    __table_args__ = (
        Index('idx_subscriber_auth', 'username', 'domain'),
        Index('idx_subscriber_username', 'username'),
    )


class Dispatcher(Base):
    """Kamailio dispatcher table for SIP trunk routing."""
    __tablename__ = "dispatcher"
    
    id = Column(Integer, primary_key=True, index=True)
    setid = Column(Integer, nullable=False, index=True)
    destination = Column(String(255), nullable=False)
    flags = Column(Integer, default=0)
    priority = Column(Integer, default=0)
    attrs = Column(String(255), default="")
    description = Column(String(500))
    
    __table_args__ = (
        Index('idx_dispatcher_set', 'setid', 'flags'),
    )


class TrunkConfiguration(Base):
    """SIP trunk configurations."""
    __tablename__ = "trunk_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    trunk_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    provider = Column(String(100), nullable=False)
    proxy_address = Column(String(255), nullable=False)
    proxy_port = Column(Integer, default=5060)
    registrar_address = Column(String(255))
    registrar_port = Column(Integer, default=5060)
    username = Column(String(100))
    password = Column(String(255))  # Will be encrypted
    realm = Column(String(100))
    auth_method = Column(String(20), default="digest")
    transport = Column(String(10), default="UDP")
    supports_registration = Column(Boolean, default=True)
    supports_outbound = Column(Boolean, default=True)
    supports_inbound = Column(Boolean, default=True)
    dial_prefix = Column(String(20), default="")
    strip_digits = Column(Integer, default=0)
    prepend_digits = Column(String(20), default="")
    max_concurrent_calls = Column(Integer, default=100)
    calls_per_second_limit = Column(Integer, default=10)
    preferred_codecs = Column(JSON, default=["PCMU", "PCMA"])
    enable_dtmf_relay = Column(Boolean, default=True)
    rtp_timeout = Column(Integer, default=60)
    heartbeat_interval = Column(Integer, default=30)
    registration_expire = Column(Integer, default=3600)
    failover_timeout = Column(Integer, default=30)
    backup_trunks = Column(JSON, default=[])
    allowed_ips = Column(JSON, default=[])
    status = Column(String(20), default="inactive")
    failure_count = Column(Integer, default=0)
    last_registration = Column(DateTime)
    total_calls = Column(Integer, default=0)
    successful_calls = Column(Integer, default=0)
    failed_calls = Column(Integer, default=0)
    current_calls = Column(Integer, default=0)
    sms_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Database initialization
async def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


# Dependency for FastAPI
def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
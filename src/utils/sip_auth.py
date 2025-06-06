"""SIP authentication utilities with HA1 hash generation and validation."""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple
from jose import JWTError, jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from ..models.database import SIPUser, Subscriber, SIPCallSession
from ..models.schemas import SIPAuthRequest, SIPAuthResponse
from ..utils.config import get_config
import logging

logger = logging.getLogger(__name__)


class SIPAuthenticator:
    """SIP authentication handler with HA1 hash generation and validation."""
    
    def __init__(self):
        self.config = get_config()
        # Separate JWT secret for SIP user management (high security)
        self.sip_jwt_secret = self.config.security.sip_jwt_secret
        self.default_realm = self.config.sip.domain
        self.max_failed_attempts = 5
        self.lockout_duration_minutes = 30
    
    def generate_ha1_hash(self, username: str, realm: str, password: str) -> str:
        """Generate HA1 hash for SIP authentication.
        
        HA1 = MD5(username:realm:password)
        This is the standard SIP authentication hash.
        """
        ha1_string = f"{username}:{realm}:{password}"
        return hashlib.md5(ha1_string.encode('utf-8')).hexdigest()
    
    def generate_ha1b_hash(self, username: str, domain: str, realm: str, password: str) -> str:
        """Generate HA1B hash for SIP authentication.
        
        HA1B = MD5(username@domain:realm:password)
        Alternative hash format for some SIP implementations.
        """
        ha1b_string = f"{username}@{domain}:{realm}:{password}"
        return hashlib.md5(ha1b_string.encode('utf-8')).hexdigest()
    
    def create_sip_user(self, db: Session, username: str, password: str, 
                       realm: str = None, **kwargs) -> SIPUser:
        """Create a new SIP user with proper HA1 hash generation."""
        if realm is None:
            realm = self.default_realm
        
        # Check if user already exists
        existing_user = db.query(SIPUser).filter(SIPUser.username == username).first()
        if existing_user:
            raise ValueError(f"SIP user '{username}' already exists")
        
        # Generate HA1 hash
        ha1_hash = self.generate_ha1_hash(username, realm, password)
        
        # Create SIP user
        sip_user = SIPUser(
            username=username,
            password=password,  # Store plain password for potential HA1 regeneration
            ha1=ha1_hash,
            realm=realm,
            **kwargs
        )
        
        db.add(sip_user)
        db.flush()  # Get the ID
        
        # Create corresponding Kamailio subscriber entry
        self._create_subscriber_entry(db, sip_user)
        
        db.commit()
        db.refresh(sip_user)
        
        logger.info(f"Created SIP user: {username} in realm: {realm}")
        return sip_user
    
    def _create_subscriber_entry(self, db: Session, sip_user: SIPUser):
        """Create corresponding entry in Kamailio subscriber table."""
        # Check if subscriber entry already exists
        existing_subscriber = db.query(Subscriber).filter(
            Subscriber.username == sip_user.username,
            Subscriber.domain == sip_user.realm
        ).first()
        
        if existing_subscriber:
            # Update existing subscriber
            existing_subscriber.password = ""  # Leave password field empty when using HA1
            existing_subscriber.ha1 = sip_user.ha1
            existing_subscriber.ha1b = self.generate_ha1b_hash(
                sip_user.username, sip_user.realm, sip_user.realm, sip_user.password
            )
        else:
            # Create new subscriber entry
            subscriber = Subscriber(
                username=sip_user.username,
                domain=sip_user.realm,
                password="",  # Leave password field empty when using HA1
                email_address="",  # Required field, set to empty
                ha1=sip_user.ha1,
                ha1b=self.generate_ha1b_hash(
                    sip_user.username, sip_user.realm, sip_user.realm, sip_user.password
                )
            )
            db.add(subscriber)
    
    def update_sip_user_password(self, db: Session, user_id: int, new_password: str) -> SIPUser:
        """Update SIP user password and regenerate HA1 hashes."""
        sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
        if not sip_user:
            raise ValueError(f"SIP user with ID {user_id} not found")
        
        # Generate new HA1 hash
        new_ha1 = self.generate_ha1_hash(sip_user.username, sip_user.realm, new_password)
        
        # Update SIP user
        sip_user.password = new_password
        sip_user.ha1 = new_ha1
        sip_user.updated_at = datetime.now(timezone.utc)
        sip_user.failed_auth_attempts = 0  # Reset failed attempts
        sip_user.account_locked_until = None  # Remove any locks
        
        # Update subscriber entry
        subscriber = db.query(Subscriber).filter(
            Subscriber.username == sip_user.username,
            Subscriber.domain == sip_user.realm
        ).first()
        
        if subscriber:
            subscriber.password = ""  # Leave password field empty when using HA1
            subscriber.ha1 = new_ha1
            subscriber.ha1b = self.generate_ha1b_hash(
                sip_user.username, sip_user.realm, sip_user.realm, new_password
            )
        
        db.commit()
        db.refresh(sip_user)
        
        logger.info(f"Updated password for SIP user: {sip_user.username}")
        return sip_user
    
    def authenticate_sip_user(self, db: Session, auth_request: SIPAuthRequest) -> SIPAuthResponse:
        """Authenticate SIP user using digest authentication."""
        username = auth_request.username
        realm = auth_request.realm
        
        # Find SIP user
        sip_user = db.query(SIPUser).filter(
            SIPUser.username == username,
            SIPUser.realm == realm
        ).first()
        
        if not sip_user:
            logger.warning(f"SIP authentication failed: user not found - {username}@{realm}")
            return SIPAuthResponse(
                authenticated=False,
                reason="User not found"
            )
        
        # Check if account is active
        if not sip_user.is_active:
            logger.warning(f"SIP authentication failed: account inactive - {username}@{realm}")
            return SIPAuthResponse(
                authenticated=False,
                reason="Account inactive",
                account_inactive=True
            )
        
        # Check if account is blocked
        if sip_user.is_blocked:
            logger.warning(f"SIP authentication failed: account blocked - {username}@{realm}")
            return SIPAuthResponse(
                authenticated=False,
                reason="Account blocked"
            )
        
        # Check if account is locked due to failed attempts
        if sip_user.account_locked_until:
            current_time = datetime.now(timezone.utc)
            locked_until = sip_user.account_locked_until
            
            # Ensure timezone-aware comparison
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            
            if locked_until > current_time:
                logger.warning(f"SIP authentication failed: account locked - {username}@{realm}")
                return SIPAuthResponse(
                    authenticated=False,
                    reason="Account temporarily locked",
                    account_locked=True
                )
        
        # Validate digest response
        is_valid = self._validate_digest_response(sip_user, auth_request)
        
        if is_valid:
            # Successful authentication
            sip_user.failed_auth_attempts = 0
            sip_user.account_locked_until = None
            sip_user.last_seen = datetime.now(timezone.utc)
            db.commit()
            
            logger.info(f"SIP authentication successful: {username}@{realm}")
            return SIPAuthResponse(
                authenticated=True,
                user_id=sip_user.id,
                username=sip_user.username
            )
        else:
            # Failed authentication
            sip_user.failed_auth_attempts += 1
            
            # Lock account if too many failed attempts
            if sip_user.failed_auth_attempts >= self.max_failed_attempts:
                sip_user.account_locked_until = datetime.now(timezone.utc) + \
                    timedelta(minutes=self.lockout_duration_minutes)
                logger.warning(f"SIP account locked due to failed attempts: {username}@{realm}")
            
            db.commit()
            
            logger.warning(f"SIP authentication failed: invalid credentials - {username}@{realm}")
            return SIPAuthResponse(
                authenticated=False,
                reason="Invalid credentials"
            )
    
    def _validate_digest_response(self, sip_user: SIPUser, auth_request: SIPAuthRequest) -> bool:
        """Validate SIP digest authentication response."""
        # Calculate expected response
        # Response = MD5(HA1:nonce:HA2)
        # HA2 = MD5(method:uri)
        
        ha1 = sip_user.ha1
        ha2 = hashlib.md5(f"{auth_request.method}:{auth_request.uri}".encode()).hexdigest()
        
        if auth_request.qop and auth_request.cnonce and auth_request.nc:
            # With qop (quality of protection)
            expected_response = hashlib.md5(
                f"{ha1}:{auth_request.nonce}:{auth_request.nc}:{auth_request.cnonce}:{auth_request.qop}:{ha2}".encode()
            ).hexdigest()
        else:
            # Without qop (basic digest)
            expected_response = hashlib.md5(
                f"{ha1}:{auth_request.nonce}:{ha2}".encode()
            ).hexdigest()
        
        return expected_response.lower() == auth_request.response.lower()
    
    def get_active_call_count(self, db: Session, sip_user_id: int) -> int:
        """Get number of active calls for a SIP user."""
        return db.query(SIPCallSession).filter(
            SIPCallSession.sip_user_id == sip_user_id,
            SIPCallSession.call_state.in_(["ringing", "connected", "held"])
        ).count()
    
    def can_make_call(self, db: Session, sip_user_id: int) -> Tuple[bool, str]:
        """Check if SIP user can make a new call."""
        sip_user = db.query(SIPUser).filter(SIPUser.id == sip_user_id).first()
        if not sip_user:
            return False, "User not found"
        
        if not sip_user.is_active:
            return False, "Account inactive"
        
        if sip_user.is_blocked:
            return False, "Account blocked"
        
        active_calls = self.get_active_call_count(db, sip_user_id)
        if active_calls >= sip_user.max_concurrent_calls:
            return False, f"Maximum concurrent calls reached ({sip_user.max_concurrent_calls})"
        
        return True, "OK"
    
    def create_sip_management_token(self, user_id: int, username: str, 
                                   is_admin: bool = False) -> str:
        """Create JWT token for SIP user management API access."""
        payload = {
            "sub": username,
            "user_id": user_id,
            "is_admin": is_admin,
            "scope": "sip_management",
            "iat": datetime.now(timezone.utc).timestamp(),
            "exp": (datetime.now(timezone.utc) + timedelta(hours=2)).timestamp()
        }
        
        return jwt.encode(payload, self.sip_jwt_secret, algorithm="HS256")
    
    def verify_sip_management_token(self, token: str) -> Dict:
        """Verify JWT token for SIP user management."""
        try:
            payload = jwt.decode(token, self.sip_jwt_secret, algorithms=["HS256"])
            
            # Verify scope
            if payload.get("scope") != "sip_management":
                raise JWTError("Invalid token scope")
            
            return payload
        except JWTError as e:
            logger.error(f"SIP management token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate SIP management credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def generate_nonce(self) -> str:
        """Generate a secure nonce for SIP authentication."""
        return secrets.token_hex(16)
    
    def delete_sip_user(self, db: Session, user_id: int) -> bool:
        """Delete SIP user and associated subscriber entry."""
        sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
        if not sip_user:
            return False
        
        username = sip_user.username
        realm = sip_user.realm
        
        # Delete subscriber entry
        subscriber = db.query(Subscriber).filter(
            Subscriber.username == username,
            Subscriber.domain == realm
        ).first()
        if subscriber:
            db.delete(subscriber)
        
        # Delete SIP user
        db.delete(sip_user)
        db.commit()
        
        logger.info(f"Deleted SIP user: {username}@{realm}")
        return True
    
    def unlock_sip_user(self, db: Session, user_id: int) -> bool:
        """Unlock a SIP user account."""
        sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
        if not sip_user:
            return False
        
        sip_user.failed_auth_attempts = 0
        sip_user.account_locked_until = None
        sip_user.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info(f"Unlocked SIP user: {sip_user.username}@{sip_user.realm}")
        return True
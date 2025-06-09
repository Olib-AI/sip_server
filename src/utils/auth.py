"""Authentication utilities for API."""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import logging
import hmac
import hashlib
import time
from .config import get_config

logger = logging.getLogger(__name__)

# Get configuration
config = get_config()
SECRET_KEY = config.security.jwt_secret_key
SIP_JWT_SECRET = config.security.sip_jwt_secret  # SIP-specific JWT secret
ALGORITHM = config.security.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = config.security.jwt_expire_minutes
SIP_SHARED_SECRET = config.security.sip_shared_secret

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Get current user from JWT token."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Return user info
        return {
            "username": username,
            "user_id": payload.get("user_id"),
            "is_admin": payload.get("is_admin", False)
        }
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(current_user: dict = Depends(get_current_user)) -> Dict:
    """Require admin privileges."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


def generate_api_key() -> str:
    """Generate a new API key."""
    import secrets
    return secrets.token_urlsafe(32)


def verify_api_key(api_key: str) -> Optional[Dict]:
    """Verify an API key and return user info."""
    # Check against configured API key
    if api_key == config.security.api_key:
        return {
            "username": "api_user",
            "user_id": 1,
            "is_admin": True
        }
    return None


def verify_token(token: str) -> Dict:
    """Verify a JWT token and return user info."""
    try:
        payload = decode_token(token)
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


class WebSocketAuthenticator:
    """WebSocket authentication handler."""
    
    def __init__(self):
        self.config = get_config()
    
    def verify_websocket_token(self, token: str) -> Dict:
        """Verify WebSocket authentication token."""
        try:
            if not token:
                raise ValueError("No token provided")
            
            # Support both JWT tokens and API keys
            if token.startswith("Bearer "):
                jwt_token = token[7:]  # Remove "Bearer " prefix
                return self.verify_jwt_token(jwt_token)
            elif token.startswith("ApiKey "):
                api_key = token[7:]  # Remove "ApiKey " prefix
                return self.verify_api_key_auth(api_key)
            else:
                # Try as JWT token directly
                return self.verify_jwt_token(token)
                
        except Exception as e:
            logger.error(f"WebSocket authentication error: {e}")
            raise ValueError(f"Authentication failed: {str(e)}")
    
    def verify_jwt_token(self, token: str) -> Dict:
        """Verify JWT token for WebSocket."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check if token is expired
            exp = payload.get("exp")
            if exp and datetime.now(timezone.utc).timestamp() > exp:
                raise ValueError("Token expired")
            
            return {
                "user_id": payload.get("user_id"),
                "username": payload.get("sub"),
                "is_admin": payload.get("is_admin", False),
                "auth_method": "jwt"
            }
        except JWTError as e:
            raise ValueError(f"Invalid JWT token: {str(e)}")
    
    def verify_api_key_auth(self, api_key: str) -> Dict:
        """Verify API key for WebSocket."""
        user_info = verify_api_key(api_key)
        if not user_info:
            raise ValueError("Invalid API key")
        
        user_info["auth_method"] = "api_key"
        return user_info
    
    def verify_call_permissions(self, user_info: Dict, call_id: str) -> bool:
        """Verify user has permissions for specific call."""
        # For now, allow all authenticated users
        # In production, implement proper call ownership checks
        return True
    
    def create_websocket_token(self, call_id: str, instance_id: str = "sip_server_1") -> str:
        """Create a WebSocket-specific token for SIP authentication."""
        current_time = datetime.now(timezone.utc)
        
        # Create payload exactly as AI platform expects
        payload = {
            "call_id": call_id,
            "instance_id": instance_id,
            "source": "sip_server",  # Required by AI platform
            "iat": int(current_time.timestamp()),
            "exp": int((current_time + timedelta(hours=1)).timestamp())
        }
        
        # Use SIP-specific JWT secret
        encoded_jwt = jwt.encode(payload, SIP_JWT_SECRET, algorithm=ALGORITHM)
        return encoded_jwt
    
    def create_hmac_signature(self, call_id: str, timestamp: str) -> str:
        """Create HMAC signature for authentication."""
        message = f"{call_id}:{timestamp}"
        signature = hmac.new(
            SIP_SHARED_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def create_sip_auth_message(self, call_id: str, from_number: str, to_number: str, 
                               direction: str = "incoming", codec: str = "PCMU",
                               sample_rate: int = 8000) -> Dict:
        """Create complete authentication message for SIP WebSocket connection."""
        timestamp = str(int(time.time()))
        
        # Create JWT token for this call with simplified payload
        token = self.create_websocket_token(call_id=call_id)
        
        # Create HMAC signature
        signature = self.create_hmac_signature(call_id, timestamp)
        
        # Build complete auth message
        auth_message = {
            "type": "auth",
            "auth": {
                "token": f"Bearer {token}",
                "signature": signature,
                "timestamp": timestamp,
                "call_id": call_id
            },
            "call": {
                "conversation_id": call_id,  # Use call_id as conversation_id
                "from_number": from_number,
                "to_number": to_number,
                "direction": direction,
                "sip_headers": {},
                "codec": codec,
                "sample_rate": sample_rate
            }
        }
        
        return auth_message


# Alias for backward compatibility
create_jwt_token = create_access_token
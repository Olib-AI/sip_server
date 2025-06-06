"""Tests for SIP user authentication system."""
import pytest
import hashlib
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.database import Base, SIPUser, Subscriber, SIPCallSession
from src.utils.sip_auth import SIPAuthenticator
from src.models.schemas import SIPAuthRequest, SIPUserCreate
from src.utils.config import get_config


class TestSIPAuthenticator:
    """Test SIP authentication functionality."""
    
    @pytest.fixture
    def db_session(self):
        """Create in-memory database session for testing."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()
    
    @pytest.fixture
    def sip_auth(self):
        """Create SIP authenticator instance."""
        return SIPAuthenticator()
    
    @pytest.fixture
    def test_user_data(self):
        """Test user data."""
        return {
            "username": "testuser",
            "password": "test123456",
            "realm": "sip.test.com",
            "display_name": "Test User"
        }
    
    def test_generate_ha1_hash(self, sip_auth):
        """Test HA1 hash generation."""
        username = "testuser"
        realm = "sip.test.com"
        password = "test123456"
        
        ha1 = sip_auth.generate_ha1_hash(username, realm, password)
        
        # Verify hash format
        assert len(ha1) == 32
        assert ha1.isalnum()
        
        # Verify hash calculation
        expected = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        assert ha1 == expected
    
    def test_generate_ha1b_hash(self, sip_auth):
        """Test HA1B hash generation."""
        username = "testuser"
        domain = "sip.test.com"
        realm = "sip.test.com"
        password = "test123456"
        
        ha1b = sip_auth.generate_ha1b_hash(username, domain, realm, password)
        
        # Verify hash format
        assert len(ha1b) == 32
        assert ha1b.isalnum()
        
        # Verify hash calculation
        expected = hashlib.md5(f"{username}@{domain}:{realm}:{password}".encode()).hexdigest()
        assert ha1b == expected
    
    def test_create_sip_user(self, sip_auth, db_session, test_user_data):
        """Test SIP user creation."""
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"],
            display_name=test_user_data["display_name"]
        )
        
        # Verify user creation
        assert sip_user.id is not None
        assert sip_user.username == test_user_data["username"]
        assert sip_user.password == test_user_data["password"]
        assert sip_user.realm == test_user_data["realm"]
        assert sip_user.display_name == test_user_data["display_name"]
        assert sip_user.is_active is True
        assert sip_user.is_blocked is False
        
        # Verify HA1 hash
        expected_ha1 = hashlib.md5(
            f"{test_user_data['username']}:{test_user_data['realm']}:{test_user_data['password']}".encode()
        ).hexdigest()
        assert sip_user.ha1 == expected_ha1
        
        # Verify subscriber entry created
        subscriber = db_session.query(Subscriber).filter(
            Subscriber.username == test_user_data["username"],
            Subscriber.domain == test_user_data["realm"]
        ).first()
        
        assert subscriber is not None
        assert subscriber.username == test_user_data["username"]
        assert subscriber.domain == test_user_data["realm"]
        assert subscriber.ha1 == expected_ha1
    
    def test_create_duplicate_user(self, sip_auth, db_session, test_user_data):
        """Test creating duplicate SIP user fails."""
        # Create first user
        sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            sip_auth.create_sip_user(
                db=db_session,
                username=test_user_data["username"],
                password="different_password",
                realm=test_user_data["realm"]
            )
    
    def test_update_sip_user_password(self, sip_auth, db_session, test_user_data):
        """Test updating SIP user password."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        original_ha1 = sip_user.ha1
        new_password = "newpassword123"
        
        # Update password
        updated_user = sip_auth.update_sip_user_password(
            db=db_session,
            user_id=sip_user.id,
            new_password=new_password
        )
        
        # Verify password update
        assert updated_user.password == new_password
        assert updated_user.ha1 != original_ha1
        
        # Verify new HA1 hash
        expected_ha1 = hashlib.md5(
            f"{test_user_data['username']}:{test_user_data['realm']}:{new_password}".encode()
        ).hexdigest()
        assert updated_user.ha1 == expected_ha1
        
        # Verify failed attempts reset
        assert updated_user.failed_auth_attempts == 0
        assert updated_user.account_locked_until is None
        
        # Verify subscriber entry updated
        subscriber = db_session.query(Subscriber).filter(
            Subscriber.username == test_user_data["username"]
        ).first()
        assert subscriber.ha1 == expected_ha1
    
    def test_authenticate_sip_user_success(self, sip_auth, db_session, test_user_data):
        """Test successful SIP user authentication."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        # Create auth request with valid response
        nonce = "1234567890abcdef"
        method = "REGISTER"
        uri = f"sip:{test_user_data['realm']}"
        
        # Calculate expected response
        ha1 = sip_user.ha1
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        expected_response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        
        auth_request = SIPAuthRequest(
            username=test_user_data["username"],
            realm=test_user_data["realm"],
            method=method,
            uri=uri,
            nonce=nonce,
            response=expected_response
        )
        
        # Authenticate
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        # Verify success
        assert result.authenticated is True
        assert result.user_id == sip_user.id
        assert result.username == test_user_data["username"]
        assert result.reason is None
        
        # Verify user state updated
        db_session.refresh(sip_user)
        assert sip_user.failed_auth_attempts == 0
        assert sip_user.last_seen is not None
    
    def test_authenticate_sip_user_invalid_credentials(self, sip_auth, db_session, test_user_data):
        """Test authentication with invalid credentials."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        # Create auth request with invalid response
        auth_request = SIPAuthRequest(
            username=test_user_data["username"],
            realm=test_user_data["realm"],
            method="REGISTER",
            uri=f"sip:{test_user_data['realm']}",
            nonce="1234567890abcdef",
            response="invalid_response_hash"
        )
        
        # Authenticate
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        # Verify failure
        assert result.authenticated is False
        assert result.reason == "Invalid credentials"
        
        # Verify failed attempts incremented
        db_session.refresh(sip_user)
        assert sip_user.failed_auth_attempts == 1
    
    def test_authenticate_nonexistent_user(self, sip_auth, db_session):
        """Test authentication for nonexistent user."""
        auth_request = SIPAuthRequest(
            username="nonexistent",
            realm="sip.test.com",
            method="REGISTER",
            uri="sip:sip.test.com",
            nonce="1234567890abcdef",
            response="some_response"
        )
        
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        assert result.authenticated is False
        assert result.reason == "User not found"
    
    def test_authenticate_inactive_user(self, sip_auth, db_session, test_user_data):
        """Test authentication for inactive user."""
        # Create inactive user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"],
            is_active=False
        )
        
        auth_request = SIPAuthRequest(
            username=test_user_data["username"],
            realm=test_user_data["realm"],
            method="REGISTER",
            uri=f"sip:{test_user_data['realm']}",
            nonce="1234567890abcdef",
            response="some_response"
        )
        
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        assert result.authenticated is False
        assert result.reason == "Account inactive"
        assert result.account_inactive is True
    
    def test_authenticate_blocked_user(self, sip_auth, db_session, test_user_data):
        """Test authentication for blocked user."""
        # Create blocked user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"],
            is_blocked=True
        )
        
        auth_request = SIPAuthRequest(
            username=test_user_data["username"],
            realm=test_user_data["realm"],
            method="REGISTER",
            uri=f"sip:{test_user_data['realm']}",
            nonce="1234567890abcdef",
            response="some_response"
        )
        
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        assert result.authenticated is False
        assert result.reason == "Account blocked"
    
    def test_account_lockout_after_failed_attempts(self, sip_auth, db_session, test_user_data):
        """Test account lockout after multiple failed attempts."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        # Create invalid auth request
        auth_request = SIPAuthRequest(
            username=test_user_data["username"],
            realm=test_user_data["realm"],
            method="REGISTER",
            uri=f"sip:{test_user_data['realm']}",
            nonce="1234567890abcdef",
            response="invalid_response"
        )
        
        # Make multiple failed attempts
        for i in range(sip_auth.max_failed_attempts):
            result = sip_auth.authenticate_sip_user(db_session, auth_request)
            assert result.authenticated is False
        
        # Verify account is locked
        db_session.refresh(sip_user)
        assert sip_user.failed_auth_attempts >= sip_auth.max_failed_attempts
        assert sip_user.account_locked_until is not None
        # Ensure timezone-aware comparison
        current_time = datetime.now(timezone.utc)
        if sip_user.account_locked_until.tzinfo is None:
            # Convert to timezone-aware if needed
            import pytz
            sip_user.account_locked_until = sip_user.account_locked_until.replace(tzinfo=timezone.utc)
        assert sip_user.account_locked_until > current_time
        
        # Test authentication with locked account
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        assert result.authenticated is False
        assert result.reason == "Account temporarily locked"
        assert result.account_locked is True
    
    def test_get_active_call_count(self, sip_auth, db_session, test_user_data):
        """Test getting active call count for user."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        # Initially no active calls
        assert sip_auth.get_active_call_count(db_session, sip_user.id) == 0
        
        # Add active calls
        for i, state in enumerate(["ringing", "connected", "held"]):
            call_session = SIPCallSession(
                call_id=f"call_{i}",
                sip_user_id=sip_user.id,
                from_uri=f"sip:test{i}@test.com",
                to_uri="sip:target@test.com",
                call_direction="outbound",
                call_state=state,
                start_time=datetime.now(timezone.utc)
            )
            db_session.add(call_session)
        
        # Add ended call (should not count)
        ended_call = SIPCallSession(
            call_id="ended_call",
            sip_user_id=sip_user.id,
            from_uri="sip:ended@test.com",
            to_uri="sip:target@test.com",
            call_direction="outbound",
            call_state="ended",
            start_time=datetime.now(timezone.utc)
        )
        db_session.add(ended_call)
        db_session.commit()
        
        # Should count 3 active calls
        assert sip_auth.get_active_call_count(db_session, sip_user.id) == 3
    
    def test_can_make_call(self, sip_auth, db_session, test_user_data):
        """Test checking if user can make a call."""
        # Create user with max 2 concurrent calls
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"],
            max_concurrent_calls=2
        )
        
        # Should be able to make call initially
        can_call, reason = sip_auth.can_make_call(db_session, sip_user.id)
        assert can_call is True
        assert reason == "OK"
        
        # Add 2 active calls
        for i in range(2):
            call_session = SIPCallSession(
                call_id=f"call_{i}",
                sip_user_id=sip_user.id,
                from_uri=f"sip:test{i}@test.com",
                to_uri="sip:target@test.com",
                call_direction="outbound",
                call_state="connected",
                start_time=datetime.now(timezone.utc)
            )
            db_session.add(call_session)
        db_session.commit()
        
        # Should not be able to make more calls
        can_call, reason = sip_auth.can_make_call(db_session, sip_user.id)
        assert can_call is False
        assert "Maximum concurrent calls reached" in reason
    
    def test_unlock_sip_user(self, sip_auth, db_session, test_user_data):
        """Test unlocking a SIP user account."""
        # Create locked user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        # Lock the account
        sip_user.failed_auth_attempts = 5
        sip_user.account_locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        db_session.commit()
        
        # Unlock the account
        result = sip_auth.unlock_sip_user(db_session, sip_user.id)
        assert result is True
        
        # Verify account unlocked
        db_session.refresh(sip_user)
        assert sip_user.failed_auth_attempts == 0
        assert sip_user.account_locked_until is None
    
    def test_delete_sip_user(self, sip_auth, db_session, test_user_data):
        """Test deleting a SIP user."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_user_data["username"],
            password=test_user_data["password"],
            realm=test_user_data["realm"]
        )
        
        user_id = sip_user.id
        
        # Delete user
        result = sip_auth.delete_sip_user(db_session, user_id)
        assert result is True
        
        # Verify user deleted
        deleted_user = db_session.query(SIPUser).filter(SIPUser.id == user_id).first()
        assert deleted_user is None
        
        # Verify subscriber entry deleted
        subscriber = db_session.query(Subscriber).filter(
            Subscriber.username == test_user_data["username"]
        ).first()
        assert subscriber is None
    
    def test_generate_nonce(self, sip_auth):
        """Test nonce generation."""
        nonce1 = sip_auth.generate_nonce()
        nonce2 = sip_auth.generate_nonce()
        
        # Verify nonce format
        assert len(nonce1) == 32  # 16 bytes = 32 hex chars
        assert nonce1.isalnum()
        
        # Verify nonces are unique
        assert nonce1 != nonce2
    
    @patch('src.utils.sip_auth.get_config')
    def test_create_sip_management_token(self, mock_config, sip_auth):
        """Test SIP management token creation."""
        # Mock config
        mock_config.return_value.security.sip_jwt_secret = "test-secret"
        
        # Create token
        token = sip_auth.create_sip_management_token(
            user_id=123,
            username="testuser",
            is_admin=True
        )
        
        # Verify token format
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long
        assert token.count('.') == 2  # JWT has 3 parts separated by dots
    
    @patch('src.utils.sip_auth.get_config')
    def test_verify_sip_management_token(self, mock_config, sip_auth):
        """Test SIP management token verification."""
        # Mock config
        mock_config.return_value.security.sip_jwt_secret = "test-secret"
        
        # Create and verify token
        token = sip_auth.create_sip_management_token(
            user_id=123,
            username="testuser",
            is_admin=True
        )
        
        payload = sip_auth.verify_sip_management_token(token)
        
        # Verify payload
        assert payload["sub"] == "testuser"
        assert payload["user_id"] == 123
        assert payload["is_admin"] is True
        assert payload["scope"] == "sip_management"
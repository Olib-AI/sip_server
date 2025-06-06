"""Integration tests for SIP user functionality (without FastAPI)."""
import pytest
from unittest.mock import patch, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

from src.models.database import Base, SIPUser, Subscriber
from src.utils.sip_auth import SIPAuthenticator
from src.models.schemas import SIPUserCreate, SIPAuthRequest


class TestSIPUserFunctionality:
    """Integration tests for SIP user functionality."""
    
    @pytest.fixture
    def db_session(self):
        """Create test database session."""
        # Use in-memory SQLite for testing
        engine = create_engine("sqlite:///:memory:", echo=False)
        
        # Create all tables
        Base.metadata.create_all(engine)
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        yield session
        
        session.close()
        engine.dispose()
    
    @pytest.fixture
    def sip_auth(self):
        """Create SIP authenticator with mocked config."""
        with patch('src.utils.sip_auth.get_config') as mock_config:
            mock_config.return_value.security.sip_jwt_secret = "test-secret-key"
            mock_config.return_value.sip.domain = "test.com"
            return SIPAuthenticator()
    
    def test_create_sip_user_integration(self, db_session, sip_auth):
        """Test complete SIP user creation workflow."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password="testpass123",
            realm="sip.test.com",
            display_name="Test User",
            max_concurrent_calls=3
        )
        
        # Verify user created
        assert sip_user.id is not None
        assert sip_user.username == "testuser"
        assert sip_user.realm == "sip.test.com"
        assert sip_user.display_name == "Test User"
        assert sip_user.is_active is True
        assert sip_user.max_concurrent_calls == 3
        
        # Verify HA1 hash generated
        assert sip_user.ha1 is not None
        assert len(sip_user.ha1) == 32  # MD5 hash length
        
        # Verify subscriber entry created
        subscriber = db_session.query(Subscriber).filter(
            Subscriber.username == "testuser",
            Subscriber.domain == "sip.test.com"
        ).first()
        
        assert subscriber is not None
        assert subscriber.ha1 == sip_user.ha1
    
    def test_duplicate_user_prevention(self, db_session, sip_auth):
        """Test that duplicate users are prevented."""
        # Create first user
        sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password="password1",
            realm="sip.test.com"
        )
        
        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            sip_auth.create_sip_user(
                db=db_session,
                username="testuser",
                password="password2",
                realm="sip.test.com"
            )
    
    def test_authentication_workflow(self, db_session, sip_auth):
        """Test complete authentication workflow."""
        # Create user
        password = "testpass123"
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password=password,
            realm="sip.test.com"
        )
        
        # Test valid authentication
        nonce = sip_auth.generate_nonce()
        method = "REGISTER"
        uri = "sip:sip.test.com"
        
        # Calculate correct response
        import hashlib
        ha1 = sip_user.ha1
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        
        auth_request = SIPAuthRequest(
            username="testuser",
            realm="sip.test.com",
            method=method,
            uri=uri,
            nonce=nonce,
            response=response
        )
        
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        assert result.authenticated is True
        assert result.user_id == sip_user.id
        assert result.username == "testuser"
        
        # Test invalid authentication
        auth_request.response = "invalid_response"
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        
        assert result.authenticated is False
        assert result.reason == "Invalid credentials"
    
    def test_account_lockout_integration(self, db_session, sip_auth):
        """Test account lockout functionality."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password="testpass123",
            realm="sip.test.com"
        )
        
        # Create invalid auth request
        auth_request = SIPAuthRequest(
            username="testuser",
            realm="sip.test.com",
            method="REGISTER",
            uri="sip:sip.test.com",
            nonce="test_nonce",
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
        
        # Test authentication with locked account
        result = sip_auth.authenticate_sip_user(db_session, auth_request)
        assert result.authenticated is False
        assert result.reason == "Account temporarily locked"
        assert result.account_locked is True
        
        # Test unlock functionality
        unlock_result = sip_auth.unlock_sip_user(db_session, sip_user.id)
        assert unlock_result is True
        
        # Verify account unlocked
        db_session.refresh(sip_user)
        assert sip_user.failed_auth_attempts == 0
        assert sip_user.account_locked_until is None
    
    def test_password_update_integration(self, db_session, sip_auth):
        """Test password update functionality."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password="oldpassword",
            realm="sip.test.com"
        )
        
        original_ha1 = sip_user.ha1
        
        # Update password
        updated_user = sip_auth.update_sip_user_password(
            db=db_session,
            user_id=sip_user.id,
            new_password="newpassword123"
        )
        
        # Verify password updated
        assert updated_user.password == "newpassword123"
        assert updated_user.ha1 != original_ha1
        
        # Verify subscriber table updated
        subscriber = db_session.query(Subscriber).filter(
            Subscriber.username == "testuser"
        ).first()
        assert subscriber.ha1 == updated_user.ha1
        
        # Verify failed attempts reset
        assert updated_user.failed_auth_attempts == 0
        assert updated_user.account_locked_until is None
    
    def test_user_deletion_integration(self, db_session, sip_auth):
        """Test user deletion functionality."""
        # Create user
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password="testpass123",
            realm="sip.test.com"
        )
        
        user_id = sip_user.id
        
        # Delete user
        result = sip_auth.delete_sip_user(db_session, user_id)
        assert result is True
        
        # Verify user deleted from both tables
        deleted_user = db_session.query(SIPUser).filter(SIPUser.id == user_id).first()
        assert deleted_user is None
        
        deleted_subscriber = db_session.query(Subscriber).filter(
            Subscriber.username == "testuser"
        ).first()
        assert deleted_subscriber is None
    
    def test_concurrent_call_limits(self, db_session, sip_auth):
        """Test concurrent call limit functionality."""
        # Create user with max 2 concurrent calls
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username="testuser",
            password="testpass123",
            realm="sip.test.com",
            max_concurrent_calls=2
        )
        
        # Initially should be able to make calls
        can_call, reason = sip_auth.can_make_call(db_session, sip_user.id)
        assert can_call is True
        assert reason == "OK"
        
        # Test with no active calls
        assert sip_auth.get_active_call_count(db_session, sip_user.id) == 0
    
    def test_jwt_token_management(self, sip_auth):
        """Test JWT token creation and verification."""
        # Create token
        token = sip_auth.create_sip_management_token(
            user_id=123,
            username="admin",
            is_admin=True
        )
        
        # Verify token format
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long
        assert token.count('.') == 2  # JWT has 3 parts
        
        # Verify token
        payload = sip_auth.verify_sip_management_token(token)
        
        assert payload["sub"] == "admin"
        assert payload["user_id"] == 123
        assert payload["is_admin"] is True
        assert payload["scope"] == "sip_management"
    
    def test_nonce_generation(self, sip_auth):
        """Test nonce generation."""
        nonce1 = sip_auth.generate_nonce()
        nonce2 = sip_auth.generate_nonce()
        
        # Verify format
        assert len(nonce1) == 32  # 16 bytes = 32 hex chars
        assert nonce1.isalnum()
        
        # Verify uniqueness
        assert nonce1 != nonce2
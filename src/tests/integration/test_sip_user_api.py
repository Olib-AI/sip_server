"""Integration tests for SIP user management API."""
import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

from src.api.main import app
from src.models.database import Base, get_db, SIPUser, Subscriber
from src.models.schemas import SIPUserCreate, SIPUserUpdate
from src.utils.sip_auth import SIPAuthenticator


class TestSIPUserAPI:
    """Integration tests for SIP user management API endpoints."""
    
    @pytest.fixture
    def db_session(self):
        """Create test database session."""
        engine = create_engine("sqlite:///:memory:")
        
        # Create all tables including SIP user tables
        Base.metadata.create_all(engine)
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Override the dependency
        def override_get_db():
            try:
                yield session
            finally:
                pass
        
        app.dependency_overrides[get_db] = override_get_db
        yield session
        session.close()
        app.dependency_overrides.clear()
    
    @pytest.fixture
    def client(self, db_session):
        """Create test client with dependency overrides."""
        # Import SIP user routes to access dependencies
        from src.api.routes.sip_users import require_sip_admin
        
        # Mock admin user for all tests
        def mock_require_sip_admin():
            return {
                "username": "admin",
                "user_id": 1,
                "is_admin": True
            }
        
        # Override the dependency
        app.dependency_overrides[require_sip_admin] = mock_require_sip_admin
        
        client = TestClient(app)
        yield client
        
        # Clean up overrides
        app.dependency_overrides.clear()
    
    @pytest.fixture
    def admin_user_token(self):
        """Admin user token (not actually used since we override dependencies)."""
        yield "Bearer mock-admin-token"
    
    @pytest.fixture
    def test_sip_user_data(self):
        """Test SIP user data."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "display_name": "Test User",
            "realm": "sip.test.com",
            "max_concurrent_calls": 3,
            "call_recording_enabled": True,
            "sms_enabled": True
        }
    
    def test_create_sip_user_success(self, client, admin_user_token, test_sip_user_data):
        """Test successful SIP user creation."""
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        
        response = client.post(
            "/api/sip-users/",
            json=test_sip_user_data,
            headers=headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response data
        assert data["username"] == test_sip_user_data["username"]
        assert data["display_name"] == test_sip_user_data["display_name"]
        assert data["realm"] == test_sip_user_data["realm"]
        assert data["is_active"] is True
        assert data["is_blocked"] is False
        assert data["max_concurrent_calls"] == test_sip_user_data["max_concurrent_calls"]
        assert "id" in data
        assert "created_at" in data
        assert "password" not in data  # Password should not be returned
    
    def test_create_sip_user_unauthorized(self, db_session, test_sip_user_data):
        """Test SIP user creation without admin privileges."""
        # Create a separate client with non-admin user override
        from src.api.routes.sip_users import require_sip_admin
        from fastapi import HTTPException, status
        
        def mock_require_non_admin():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SIP user management requires admin privileges"
            )
        
        # Override with non-admin dependency
        app.dependency_overrides[require_sip_admin] = mock_require_non_admin
        
        client = TestClient(app)
        headers = {"Authorization": "Bearer user-token"}
        
        response = client.post(
            "/api/sip-users/",
            json=test_sip_user_data,
            headers=headers
        )
        
        assert response.status_code == 403
        assert "admin privileges" in response.json()["detail"]
        
        # Restore admin override
        def mock_require_sip_admin():
            return {
                "username": "admin",
                "user_id": 1,
                "is_admin": True
            }
        app.dependency_overrides[require_sip_admin] = mock_require_sip_admin
    
    def test_create_sip_user_duplicate_username(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test creating SIP user with duplicate username."""
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        
        # Create first user
        response1 = client.post(
            "/api/sip-users/",
            json=test_sip_user_data,
            headers=headers
        )
        assert response1.status_code == 201
        
        # Try to create duplicate
        response2 = client.post(
            "/api/sip-users/",
            json=test_sip_user_data,
            headers=headers
        )
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]
    
    def test_create_sip_user_invalid_data(self, client, admin_user_token):
        """Test SIP user creation with invalid data."""
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        
        # Invalid username (too short)
        invalid_data = {
            "username": "ab",  # Too short
            "password": "testpass123"
        }
        
        response = client.post(
            "/api/sip-users/",
            json=invalid_data,
            headers=headers
        )
        assert response.status_code == 422  # Validation error
    
    def test_list_sip_users(self, client, admin_user_token, db_session):
        """Test listing SIP users."""
        # Create test users
        sip_auth = SIPAuthenticator()
        for i in range(3):
            sip_auth.create_sip_user(
                db=db_session,
                username=f"user{i}",
                password=f"pass{i}",
                realm="sip.test.com",
                display_name=f"User {i}"
            )
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get("/api/sip-users/", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["per_page"] == 50
        assert len(data["users"]) == 3
        assert data["users"][0]["username"] == "user0"
    
    def test_list_sip_users_with_pagination(self, client, admin_user_token, db_session):
        """Test listing SIP users with pagination."""
        # Create test users
        sip_auth = SIPAuthenticator()
        for i in range(5):
            sip_auth.create_sip_user(
                db=db_session,
                username=f"user{i}",
                password=f"pass{i}",
                realm="sip.test.com"
            )
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get(
            "/api/sip-users/?page=1&per_page=2",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert len(data["users"]) == 2
    
    def test_list_sip_users_with_search(self, client, admin_user_token, db_session):
        """Test listing SIP users with search."""
        # Create test users
        sip_auth = SIPAuthenticator()
        sip_auth.create_sip_user(
            db=db_session,
            username="alice",
            password="pass1",
            realm="sip.test.com",
            display_name="Alice Smith"
        )
        sip_auth.create_sip_user(
            db=db_session,
            username="bob",
            password="pass2",
            realm="sip.test.com",
            display_name="Bob Jones"
        )
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get(
            "/api/sip-users/?search=alice",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 1
        assert data["users"][0]["username"] == "alice"
    
    def test_get_sip_user(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test getting individual SIP user."""
        # Create user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"],
            display_name=test_sip_user_data["display_name"]
        )
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get(f"/api/sip-users/{sip_user.id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == sip_user.id
        assert data["username"] == test_sip_user_data["username"]
        assert data["display_name"] == test_sip_user_data["display_name"]
        assert "password" not in data
    
    def test_get_sip_user_not_found(self, client, admin_user_token):
        """Test getting non-existent SIP user."""
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get("/api/sip-users/999", headers=headers)
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_update_sip_user(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test updating SIP user."""
        # Create user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"]
        )
        
        # Update data
        update_data = {
            "display_name": "Updated Name",
            "max_concurrent_calls": 5,
            "is_active": False
        }
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.put(
            f"/api/sip-users/{sip_user.id}",
            json=update_data,
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["display_name"] == "Updated Name"
        assert data["max_concurrent_calls"] == 5
        assert data["is_active"] is False
    
    def test_update_sip_user_password(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test updating SIP user password."""
        # Create user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"]
        )
        
        original_ha1 = sip_user.ha1
        
        # Update password
        update_data = {"password": "newpassword123"}
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.put(
            f"/api/sip-users/{sip_user.id}",
            json=update_data,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Verify password changed (HA1 hash should be different)
        db_session.refresh(sip_user)
        assert sip_user.ha1 != original_ha1
    
    def test_delete_sip_user(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test deleting SIP user."""
        # Create user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"]
        )
        
        user_id = sip_user.id
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.delete(f"/api/sip-users/{user_id}", headers=headers)
        
        assert response.status_code == 204
        
        # Verify user deleted
        deleted_user = db_session.query(SIPUser).filter(SIPUser.id == user_id).first()
        assert deleted_user is None
    
    def test_unlock_sip_user(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test unlocking SIP user."""
        # Create locked user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"]
        )
        
        # Lock the user
        sip_user.failed_auth_attempts = 5
        sip_user.account_locked_until = datetime.now(timezone.utc)
        db_session.commit()
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.post(f"/api/sip-users/{sip_user.id}/unlock", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["failed_auth_attempts"] == 0
        assert data["account_locked_until"] is None
    
    def test_get_sip_user_credentials(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test getting SIP user credentials."""
        # Create user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"]
        )
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get(f"/api/sip-users/{sip_user.id}/credentials", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["username"] == test_sip_user_data["username"]
        assert data["realm"] == test_sip_user_data["realm"]
        assert "sip_domain" in data
        assert "proxy_address" in data
        assert "proxy_port" in data
    
    def test_get_sip_user_stats(self, client, admin_user_token, db_session, test_sip_user_data):
        """Test getting SIP user statistics."""
        # Create user
        sip_auth = SIPAuthenticator()
        sip_user = sip_auth.create_sip_user(
            db=db_session,
            username=test_sip_user_data["username"],
            password=test_sip_user_data["password"],
            realm=test_sip_user_data["realm"]
        )
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.get(f"/api/sip-users/{sip_user.id}/stats", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["username"] == test_sip_user_data["username"]
        assert data["total_calls"] == 0
        assert data["total_minutes"] == 0
        assert data["total_sms"] == 0
        assert data["active_calls"] == 0
        assert data["registration_status"] == "never"
    
    def test_bulk_create_sip_users(self, client, admin_user_token):
        """Test bulk creation of SIP users."""
        users_data = [
            {
                "username": f"bulkuser{i}",
                "password": f"password{i}",
                "realm": "sip.test.com",
                "display_name": f"Bulk User {i}"
            }
            for i in range(3)
        ]
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.post(
            "/api/sip-users/bulk-create",
            json=users_data,
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 3
        for i, user in enumerate(data):
            assert user["username"] == f"bulkuser{i}"
            assert user["display_name"] == f"Bulk User {i}"
    
    def test_bulk_create_too_many_users(self, client, admin_user_token):
        """Test bulk creation with too many users."""
        users_data = [
            {
                "username": f"user{i}",
                "password": f"password{i}",
                "realm": "sip.test.com"
            }
            for i in range(101)  # More than limit
        ]
        
        headers = {"Authorization": f"Bearer {admin_user_token}"}
        response = client.post(
            "/api/sip-users/bulk-create",
            json=users_data,
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Maximum 100 users" in response.json()["detail"]
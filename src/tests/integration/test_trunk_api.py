"""Integration tests for trunk management API endpoints."""
import pytest
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ...api.main import app
from ...models.database import Base, TrunkConfiguration, get_db
from ...utils.auth import create_jwt_token


# Test database setup - using in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    """Create test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def clean_db():
    """Clean database before each test."""
    db = TestingSessionLocal()
    try:
        # Delete all trunk configurations
        db.query(TrunkConfiguration).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def auth_headers():
    """Create valid authentication headers."""
    token = create_jwt_token({"sub": "test_user", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_trunk_data():
    """Sample trunk data for testing."""
    return {
        "trunk_id": "skyetel_test",
        "name": "Skyetel Test Trunk",
        "provider": "skyetel",
        "proxy_address": "sip.skyetel.com",
        "proxy_port": 5060,
        "username": "test_user",
        "password": "test_password",
        "realm": "sip.skyetel.com",
        "transport": "UDP",
        "supports_outbound": True,
        "supports_inbound": True,
        "preferred_codecs": ["PCMU", "PCMA"],
        "max_concurrent_calls": 100,
        "calls_per_second_limit": 10
    }


class TestTrunkCreation:
    """Test trunk creation endpoints."""
    
    def test_create_trunk_success(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test successful trunk creation."""
        response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Trunk created successfully"
        assert data["trunk_id"] == "skyetel_test"
        assert "id" in data
    
    def test_create_trunk_duplicate_id(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test creating trunk with duplicate trunk_id."""
        # Create first trunk
        response1 = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert response1.status_code == 201
        
        # Try to create second trunk with same trunk_id
        response2 = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]
    
    def test_create_trunk_invalid_data(self, client, clean_db, auth_headers):
        """Test trunk creation with invalid data."""
        invalid_data = {
            "trunk_id": "invalid trunk id",  # Invalid characters
            "name": "",  # Empty name
            "provider": "",  # Empty provider
            "proxy_address": "invalid_address"
        }
        
        response = client.post(
            "/api/trunks/",
            json=invalid_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_create_trunk_unauthorized(self, client, clean_db, sample_trunk_data):
        """Test trunk creation without authentication."""
        response = client.post(
            "/api/trunks/",
            json=sample_trunk_data
        )
        
        assert response.status_code == 401


class TestTrunkRetrieval:
    """Test trunk retrieval endpoints."""
    
    def test_list_trunks_empty(self, client, clean_db, auth_headers):
        """Test listing trunks when none exist."""
        response = client.get("/api/trunks/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["trunks"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["per_page"] == 20
    
    def test_list_trunks_with_data(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test listing trunks with existing data."""
        # Create a trunk first
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # List trunks
        response = client.get("/api/trunks/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["trunks"]) == 1
        assert data["total"] == 1
        assert data["trunks"][0]["trunk_id"] == "skyetel_test"
        assert data["trunks"][0]["name"] == "Skyetel Test Trunk"
        assert data["trunks"][0]["provider"] == "skyetel"
        assert data["trunks"][0]["status"] == "inactive"  # Default status
    
    def test_list_trunks_with_pagination(self, client, clean_db, auth_headers):
        """Test trunk listing with pagination."""
        # Create multiple trunks
        for i in range(5):
            trunk_data = {
                "trunk_id": f"trunk_{i}",
                "name": f"Trunk {i}",
                "provider": "test_provider",
                "proxy_address": f"sip{i}.test.com"
            }
            response = client.post(
                "/api/trunks/",
                json=trunk_data,
                headers=auth_headers
            )
            assert response.status_code == 201
        
        # Test pagination
        response = client.get(
            "/api/trunks/?page=1&per_page=3",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["trunks"]) == 3
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["per_page"] == 3
    
    def test_list_trunks_with_filtering(self, client, clean_db, auth_headers):
        """Test trunk listing with provider filtering."""
        # Create trunks with different providers
        providers = ["skyetel", "didforsale", "skyetel"]
        for i, provider in enumerate(providers):
            trunk_data = {
                "trunk_id": f"trunk_{i}",
                "name": f"Trunk {i}",
                "provider": provider,
                "proxy_address": f"sip{i}.{provider}.com"
            }
            response = client.post(
                "/api/trunks/",
                json=trunk_data,
                headers=auth_headers
            )
            assert response.status_code == 201
        
        # Filter by provider
        response = client.get(
            "/api/trunks/?provider=skyetel",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["trunks"]) == 2
        assert data["total"] == 2
        for trunk in data["trunks"]:
            assert trunk["provider"] == "skyetel"
    
    def test_get_trunk_by_id_success(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test retrieving specific trunk by ID."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Get trunk by ID
        response = client.get(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["trunk_id"] == "skyetel_test"
        assert data["name"] == "Skyetel Test Trunk"
        assert data["provider"] == "skyetel"
        assert data["proxy_address"] == "sip.skyetel.com"
        assert data["username"] == "test_user"
        # Password should not be returned in plain text
        assert "password" not in data or data.get("password") != "test_password"
    
    def test_get_trunk_by_id_not_found(self, client, clean_db, auth_headers):
        """Test retrieving non-existent trunk."""
        response = client.get(
            "/api/trunks/nonexistent_trunk",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestTrunkUpdate:
    """Test trunk update endpoints."""
    
    def test_update_trunk_success(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test successful trunk update."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Update trunk
        update_data = {
            "name": "Updated Trunk Name",
            "max_concurrent_calls": 200,
            "calls_per_second_limit": 20
        }
        
        response = client.put(
            "/api/trunks/skyetel_test",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Trunk updated successfully"
        assert data["trunk_id"] == "skyetel_test"
        assert "updated_fields" in data
        
        # Verify changes
        get_response = client.get(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        trunk_data = get_response.json()
        assert trunk_data["name"] == "Updated Trunk Name"
        assert trunk_data["max_concurrent_calls"] == 200
        assert trunk_data["calls_per_second_limit"] == 20
    
    def test_update_trunk_not_found(self, client, clean_db, auth_headers):
        """Test updating non-existent trunk."""
        update_data = {"name": "Updated Name"}
        
        response = client.put(
            "/api/trunks/nonexistent_trunk",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_update_trunk_password(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test updating trunk password."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Update password
        update_data = {"password": "new_password_123"}
        
        response = client.put(
            "/api/trunks/skyetel_test",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        
        # Verify password was encrypted (not stored in plain text)
        # This requires checking the database directly since password isn't returned in API
        db = TestingSessionLocal()
        try:
            trunk = db.query(TrunkConfiguration).filter(
                TrunkConfiguration.trunk_id == "skyetel_test"
            ).first()
            assert trunk.password != "new_password_123"  # Should be encrypted
            assert len(trunk.password) > 0  # Should have some encrypted value
        finally:
            db.close()


class TestTrunkDeletion:
    """Test trunk deletion endpoints."""
    
    def test_delete_trunk_success(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test successful trunk deletion."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Delete trunk
        response = client.delete(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Trunk deleted successfully"
        assert data["trunk_id"] == "skyetel_test"
        
        # Verify trunk is deleted
        get_response = client.get(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        assert get_response.status_code == 404
    
    def test_delete_trunk_not_found(self, client, clean_db, auth_headers):
        """Test deleting non-existent trunk."""
        response = client.delete(
            "/api/trunks/nonexistent_trunk",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_delete_trunk_with_active_calls(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test deleting trunk with active calls."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Simulate active calls by updating current_calls directly in DB
        db = TestingSessionLocal()
        try:
            trunk = db.query(TrunkConfiguration).filter(
                TrunkConfiguration.trunk_id == "skyetel_test"
            ).first()
            trunk.current_calls = 5  # Simulate active calls
            db.commit()
        finally:
            db.close()
        
        # Try to delete trunk
        response = client.delete(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "active calls" in response.json()["detail"]


class TestTrunkActivation:
    """Test trunk activation/deactivation endpoints."""
    
    def test_activate_trunk_success(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test successful trunk activation."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Activate trunk
        response = client.post(
            "/api/trunks/skyetel_test/activate",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Trunk activated successfully"
        assert data["trunk_id"] == "skyetel_test"
        assert data["status"] == "active"
        
        # Verify status changed
        get_response = client.get(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        trunk_data = get_response.json()
        assert trunk_data["status"] == "active"
    
    def test_deactivate_trunk_success(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test successful trunk deactivation."""
        # Create and activate trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        activate_response = client.post(
            "/api/trunks/skyetel_test/activate",
            headers=auth_headers
        )
        assert activate_response.status_code == 200
        
        # Deactivate trunk
        response = client.post(
            "/api/trunks/skyetel_test/deactivate",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Trunk deactivated successfully"
        assert data["trunk_id"] == "skyetel_test"
        assert data["status"] == "inactive"
        
        # Verify status changed
        get_response = client.get(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        trunk_data = get_response.json()
        assert trunk_data["status"] == "inactive"
    
    def test_activate_nonexistent_trunk(self, client, clean_db, auth_headers):
        """Test activating non-existent trunk."""
        response = client.post(
            "/api/trunks/nonexistent_trunk/activate",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestTrunkStatus:
    """Test trunk status and statistics endpoints."""
    
    def test_get_trunk_status(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test getting trunk status."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Get trunk status
        response = client.get(
            "/api/trunks/skyetel_test/status",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["trunk_id"] == "skyetel_test"
        assert data["name"] == "Skyetel Test Trunk"
        assert data["provider"] == "skyetel"
        assert data["status"] == "inactive"
        assert data["total_calls"] == 0
        assert data["successful_calls"] == 0
        assert data["failed_calls"] == 0
        assert data["current_calls"] == 0
        assert data["success_rate"] == 0.0
        assert data["failure_count"] == 0
    
    def test_get_trunk_credentials(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test getting trunk credentials."""
        # Create trunk
        create_response = client.post(
            "/api/trunks/",
            json=sample_trunk_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        
        # Get trunk credentials
        response = client.get(
            "/api/trunks/skyetel_test/credentials",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["trunk_id"] == "skyetel_test"
        assert data["name"] == "Skyetel Test Trunk"
        assert data["provider"] == "skyetel"
        assert data["proxy_address"] == "sip.skyetel.com"
        assert data["proxy_port"] == 5060
        assert data["username"] == "test_user"
        assert data["realm"] == "sip.skyetel.com"
        assert data["transport"] == "UDP"
        assert data["preferred_codecs"] == ["PCMU", "PCMA"]
        # Password should not be included in credentials response
        assert "password" not in data
    
    def test_get_trunk_stats_summary(self, client, clean_db, auth_headers, sample_trunk_data):
        """Test getting overall trunk statistics."""
        # Create multiple trunks
        for i in range(3):
            trunk_data = sample_trunk_data.copy()
            trunk_data["trunk_id"] = f"trunk_{i}"
            trunk_data["name"] = f"Trunk {i}"
            
            response = client.post(
                "/api/trunks/",
                json=trunk_data,
                headers=auth_headers
            )
            assert response.status_code == 201
        
        # Activate one trunk
        activate_response = client.post(
            "/api/trunks/trunk_0/activate",
            headers=auth_headers
        )
        assert activate_response.status_code == 200
        
        # Get stats summary
        response = client.get(
            "/api/trunks/stats/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_trunks"] == 3
        assert data["active_trunks"] == 1
        assert data["inactive_trunks"] == 2
        assert data["total_calls"] == 0
        assert data["successful_calls"] == 0
        assert data["failed_calls"] == 0
        assert data["current_calls"] == 0
        assert data["overall_success_rate"] == 0.0


class TestTrunkAuthentication:
    """Test trunk API authentication and authorization."""
    
    def test_all_endpoints_require_auth(self, client, clean_db, sample_trunk_data):
        """Test that all trunk endpoints require authentication."""
        endpoints = [
            ("POST", "/api/trunks/", sample_trunk_data),
            ("GET", "/api/trunks/", None),
            ("GET", "/api/trunks/test_trunk", None),
            ("PUT", "/api/trunks/test_trunk", {"name": "Updated"}),
            ("DELETE", "/api/trunks/test_trunk", None),
            ("POST", "/api/trunks/test_trunk/activate", None),
            ("POST", "/api/trunks/test_trunk/deactivate", None),
            ("GET", "/api/trunks/test_trunk/status", None),
            ("GET", "/api/trunks/test_trunk/credentials", None),
            ("GET", "/api/trunks/stats/summary", None),
        ]
        
        for method, endpoint, data in endpoints:
            if method == "POST":
                response = client.post(endpoint, json=data)
            elif method == "GET":
                response = client.get(endpoint)
            elif method == "PUT":
                response = client.put(endpoint, json=data)
            elif method == "DELETE":
                response = client.delete(endpoint)
            
            assert response.status_code == 401, f"Endpoint {method} {endpoint} should require auth"
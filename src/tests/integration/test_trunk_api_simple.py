"""Integration tests for trunk management API endpoints (simplified)."""
import pytest
import os
import tempfile
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing our modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only-not-production"
os.environ["API_KEY"] = "test-api-key-for-testing-only"

from ...models.database import Base, TrunkConfiguration, get_db
from ...models.schemas import TrunkCreate, TrunkUpdate
from ...utils.auth import create_jwt_token
from ...api.routes.trunks import router as trunk_router

# Create test app with just the trunk routes
app = FastAPI()
app.include_router(trunk_router)

# Test database setup
engine = create_engine(
    "sqlite:///:memory:",
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


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create valid authentication headers."""
    token = create_jwt_token({"sub": "test_user", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def clean_db():
    """Clean database before each test."""
    db = TestingSessionLocal()
    try:
        db.query(TrunkConfiguration).delete()
        db.commit()
    finally:
        db.close()


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


class TestTrunkCRUD:
    """Test basic trunk CRUD operations."""
    
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
        assert data["trunks"][0]["status"] == "inactive"
    
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
    
    def test_get_trunk_by_id_not_found(self, client, clean_db, auth_headers):
        """Test retrieving non-existent trunk."""
        response = client.get(
            "/api/trunks/nonexistent_trunk",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
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
            "max_concurrent_calls": 200
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
        
        # Verify changes
        get_response = client.get(
            "/api/trunks/skyetel_test",
            headers=auth_headers
        )
        trunk_data = get_response.json()
        assert trunk_data["name"] == "Updated Trunk Name"
        assert trunk_data["max_concurrent_calls"] == 200
    
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
        assert data["success_rate"] == 0.0
    
    def test_create_trunk_unauthorized(self, client, clean_db, sample_trunk_data):
        """Test trunk creation without authentication."""
        response = client.post(
            "/api/trunks/",
            json=sample_trunk_data
        )
        
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden


class TestTrunkFiltering:
    """Test trunk filtering and pagination."""
    
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


class TestTrunkStatistics:
    """Test trunk statistics endpoints."""
    
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
        assert data["overall_success_rate"] == 0.0
    
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
        assert data["provider"] == "skyetel"
        assert data["proxy_address"] == "sip.skyetel.com"
        assert data["username"] == "test_user"
        assert data["transport"] == "UDP"
        assert data["preferred_codecs"] == ["PCMU", "PCMA"]
        # Password should not be included in credentials response
        assert "password" not in data
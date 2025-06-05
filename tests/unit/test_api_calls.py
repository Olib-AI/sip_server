"""Unit tests for call management API endpoints."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from src.api.main import app
from src.models.schemas import CallInfo, CallInitiate, CallTransfer


class TestCallsAPI:
    """Test suite for calls API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_auth_token(self):
        """Mock JWT token for authentication."""
        return "mock-jwt-token"
    
    @pytest.fixture
    def mock_auth_headers(self, mock_auth_token):
        """Mock authentication headers."""
        return {"Authorization": f"Bearer {mock_auth_token}"}
    
    @pytest.fixture
    def sample_call_initiate(self):
        """Sample call initiation data."""
        return {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "headers": {"X-Custom": "test"},
            "webhook_url": "https://example.com/webhook",
            "timeout": 60
        }
    
    @pytest.fixture
    def sample_call_info(self):
        """Sample call information."""
        return CallInfo(
            call_id="test-call-123",
            from_number="+1234567890",
            to_number="+0987654321",
            status="connected",
            direction="outbound",
            start_time=datetime.utcnow(),
            metadata={"test": "data"}
        )

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_initiate_call_success(self, mock_sip_client, mock_auth, client, 
                                   mock_auth_headers, sample_call_initiate, sample_call_info):
        """Test successful call initiation."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.is_number_registered.return_value = True
        mock_client_instance.initiate_call.return_value = sample_call_info
        
        # Make request
        response = client.post(
            "/api/calls/initiate",
            json=sample_call_initiate,
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["call_id"] == "test-call-123"
        assert data["from_number"] == "+1234567890"
        assert data["to_number"] == "+0987654321"
        assert data["status"] == "connected"
        
        # Verify mock calls
        mock_client_instance.is_number_registered.assert_called_once_with("+1234567890")
        mock_client_instance.initiate_call.assert_called_once()

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_initiate_call_invalid_from_number(self, mock_sip_client, mock_auth, 
                                               client, mock_auth_headers):
        """Test call initiation with invalid from number."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.is_number_registered.return_value = False
        
        # Make request
        response = client.post(
            "/api/calls/initiate",
            json={
                "from_number": "+1234567890",
                "to_number": "+0987654321"
            },
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 400
        assert "From number not registered" in response.json()["detail"]

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_get_active_calls(self, mock_sip_client, mock_auth, client, 
                              mock_auth_headers, sample_call_info):
        """Test getting active calls."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_active_calls.return_value = [sample_call_info]
        
        # Make request
        response = client.get("/api/calls/active", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["call_id"] == "test-call-123"

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_get_active_calls_with_pagination(self, mock_sip_client, mock_auth, 
                                              client, mock_auth_headers):
        """Test getting active calls with pagination."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        
        # Create multiple call objects
        calls = []
        for i in range(5):
            call = CallInfo(
                call_id=f"call-{i}",
                from_number="+1234567890",
                to_number="+0987654321",
                status="connected",
                direction="outbound",
                start_time=datetime.utcnow()
            )
            calls.append(call)
        
        mock_client_instance.get_active_calls.return_value = calls
        
        # Make request with pagination
        response = client.get(
            "/api/calls/active?limit=3&offset=1", 
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3  # Limited to 3 results
        # Should start from offset 1, so first result should be call-1
        assert data[0]["call_id"] == "call-1"

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_get_call_info(self, mock_sip_client, mock_auth, client, 
                           mock_auth_headers, sample_call_info):
        """Test getting specific call information."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = sample_call_info
        
        # Make request
        response = client.get("/api/calls/test-call-123", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["call_id"] == "test-call-123"

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_get_call_info_not_found(self, mock_sip_client, mock_auth, 
                                     client, mock_auth_headers):
        """Test getting non-existent call information."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = None
        
        # Make request
        response = client.get("/api/calls/non-existent", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 404
        assert "Call not found" in response.json()["detail"]

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_hangup_call(self, mock_sip_client, mock_auth, client, 
                         mock_auth_headers, sample_call_info):
        """Test hanging up a call."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = sample_call_info
        mock_client_instance.hangup_call.return_value = True
        
        # Make request
        response = client.post("/api/calls/test-call-123/hangup", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "terminated successfully" in data["message"]
        
        # Verify mock calls
        mock_client_instance.hangup_call.assert_called_once_with("test-call-123")

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_transfer_call(self, mock_sip_client, mock_auth, client, 
                           mock_auth_headers, sample_call_info):
        """Test transferring a call."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = sample_call_info
        mock_client_instance.transfer_call.return_value = True
        
        transfer_data = {
            "target_number": "+5555555555",
            "blind_transfer": True
        }
        
        # Make request
        response = client.post(
            "/api/calls/test-call-123/transfer", 
            json=transfer_data,
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "transferred successfully" in data["message"]
        
        # Verify mock calls
        mock_client_instance.transfer_call.assert_called_once_with(
            call_id="test-call-123",
            target_number="+5555555555",
            blind_transfer=True
        )

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_hold_call(self, mock_sip_client, mock_auth, client, 
                       mock_auth_headers, sample_call_info):
        """Test putting a call on hold."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = sample_call_info
        mock_client_instance.hold_call.return_value = True
        
        # Make request
        response = client.post("/api/calls/test-call-123/hold", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "placed on hold" in data["message"]

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_resume_call(self, mock_sip_client, mock_auth, client, 
                         mock_auth_headers, sample_call_info):
        """Test resuming a call from hold."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = sample_call_info
        mock_client_instance.resume_call.return_value = True
        
        # Make request
        response = client.post("/api/calls/test-call-123/resume", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "resumed" in data["message"]

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_send_dtmf(self, mock_sip_client, mock_auth, client, 
                       mock_auth_headers, sample_call_info):
        """Test sending DTMF digits."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = sample_call_info
        mock_client_instance.send_dtmf.return_value = True
        
        # Make request
        response = client.post(
            "/api/calls/test-call-123/dtmf?digits=123*#", 
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "123*#" in data["message"]
        
        # Verify mock calls
        mock_client_instance.send_dtmf.assert_called_once_with("test-call-123", "123*#")

    @patch('src.api.routes.calls.get_current_user')
    def test_send_dtmf_invalid_digits(self, mock_auth, client, mock_auth_headers):
        """Test sending invalid DTMF digits."""
        mock_auth.return_value = {"user_id": "test-user"}
        
        # Make request with invalid DTMF digits
        response = client.post(
            "/api/calls/test-call-123/dtmf?digits=abc", 
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error

    @patch('src.api.routes.calls.get_current_user')
    def test_unauthorized_request(self, mock_auth, client):
        """Test request without authentication."""
        mock_auth.side_effect = Exception("Unauthorized")
        
        # Make request without auth headers
        response = client.get("/api/calls/active")
        
        # Assertions
        assert response.status_code == 401

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_server_error_handling(self, mock_sip_client, mock_auth, 
                                   client, mock_auth_headers):
        """Test server error handling."""
        # Setup mocks to raise exception
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_active_calls.side_effect = Exception("Database error")
        
        # Make request
        response = client.get("/api/calls/active", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 500

    def test_invalid_request_data(self, client, mock_auth_headers):
        """Test request with invalid data."""
        # Make request with missing required fields
        response = client.post(
            "/api/calls/initiate",
            json={"from_number": "invalid"},
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_call_history_empty(self, mock_sip_client, mock_auth, 
                                client, mock_auth_headers):
        """Test getting call history when empty."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        
        # Make request
        response = client.get("/api/calls/history", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data == []  # Empty list for now

    @patch('src.api.routes.calls.get_current_user')
    @patch('src.api.routes.calls.SIPClient')
    def test_call_operations_on_non_existent_call(self, mock_sip_client, mock_auth, 
                                                   client, mock_auth_headers):
        """Test operations on non-existent call."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_client_instance = AsyncMock()
        mock_sip_client.return_value = mock_client_instance
        mock_client_instance.get_call_info.return_value = None
        
        # Test hangup on non-existent call
        response = client.post("/api/calls/non-existent/hangup", headers=mock_auth_headers)
        assert response.status_code == 404
        
        # Test transfer on non-existent call
        response = client.post(
            "/api/calls/non-existent/transfer",
            json={"target_number": "+1234567890", "blind_transfer": True},
            headers=mock_auth_headers
        )
        assert response.status_code == 404
        
        # Test hold on non-existent call
        response = client.post("/api/calls/non-existent/hold", headers=mock_auth_headers)
        assert response.status_code == 404
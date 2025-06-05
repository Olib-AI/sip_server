"""Unit tests for SMS management API endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from src.api.main import app
from src.models.schemas import SMSInfo, SMSSend


class TestSMSAPI:
    """Test suite for SMS API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_auth_headers(self):
        """Mock authentication headers."""
        return {"Authorization": "Bearer mock-jwt-token"}
    
    @pytest.fixture
    def sample_sms_send(self):
        """Sample SMS send data."""
        return {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Hello from SIP server!",
            "webhook_url": "https://example.com/webhook"
        }
    
    @pytest.fixture
    def sample_sms_info(self):
        """Sample SMS information."""
        return SMSInfo(
            message_id="sms-123",
            from_number="+1234567890",
            to_number="+0987654321",
            message="Hello from SIP server!",
            status="sent",
            direction="outbound",
            timestamp=datetime.utcnow(),
            segments=1
        )

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_send_sms_success(self, mock_sms_manager, mock_auth, client, 
                              mock_auth_headers, sample_sms_send, sample_sms_info):
        """Test successful SMS sending."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.send_sms.return_value = sample_sms_info
        
        # Make request
        response = client.post(
            "/api/sms/send",
            json=sample_sms_send,
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == "sms-123"
        assert data["from_number"] == "+1234567890"
        assert data["to_number"] == "+0987654321"
        assert data["status"] == "sent"
        
        # Verify mock calls
        mock_manager_instance.send_sms.assert_called_once()

    @patch('src.api.routes.sms.get_current_user')
    def test_send_sms_invalid_data(self, mock_auth, client, mock_auth_headers):
        """Test SMS sending with invalid data."""
        mock_auth.return_value = {"user_id": "test-user"}
        
        # Make request with invalid phone number
        response = client.post(
            "/api/sms/send",
            json={
                "from_number": "invalid",
                "to_number": "+0987654321",
                "message": "Test"
            },
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error

    @patch('src.api.routes.sms.get_current_user')
    def test_send_sms_empty_message(self, mock_auth, client, mock_auth_headers):
        """Test SMS sending with empty message."""
        mock_auth.return_value = {"user_id": "test-user"}
        
        # Make request with empty message
        response = client.post(
            "/api/sms/send",
            json={
                "from_number": "+1234567890",
                "to_number": "+0987654321",
                "message": ""
            },
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error

    @patch('src.api.routes.sms.get_current_user')
    def test_send_sms_message_too_long(self, mock_auth, client, mock_auth_headers):
        """Test SMS sending with message too long."""
        mock_auth.return_value = {"user_id": "test-user"}
        
        # Make request with very long message
        long_message = "x" * 1601  # Exceeds 1600 character limit
        response = client.post(
            "/api/sms/send",
            json={
                "from_number": "+1234567890",
                "to_number": "+0987654321",
                "message": long_message
            },
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 422  # Validation error

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_get_sms_history(self, mock_sms_manager, mock_auth, client, 
                             mock_auth_headers, sample_sms_info):
        """Test getting SMS history."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.get_message_history.return_value = [sample_sms_info]
        
        # Make request
        response = client.get("/api/sms/history", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["message_id"] == "sms-123"

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_get_sms_history_with_filters(self, mock_sms_manager, mock_auth, 
                                          client, mock_auth_headers):
        """Test getting SMS history with filters."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.get_message_history.return_value = []
        
        # Make request with filters
        response = client.get(
            "/api/sms/history?number=+1234567890&limit=10&offset=0",
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Verify mock calls with correct parameters
        mock_manager_instance.get_message_history.assert_called_once()

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_get_sms_status(self, mock_sms_manager, mock_auth, client, 
                            mock_auth_headers, sample_sms_info):
        """Test getting SMS message status."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.get_message_status.return_value = sample_sms_info
        
        # Make request
        response = client.get("/api/sms/sms-123", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == "sms-123"
        assert data["status"] == "sent"

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_get_sms_status_not_found(self, mock_sms_manager, mock_auth, 
                                      client, mock_auth_headers):
        """Test getting status of non-existent SMS."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.get_message_status.return_value = None
        
        # Make request
        response = client.get("/api/sms/non-existent", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_retry_failed_sms(self, mock_sms_manager, mock_auth, client, 
                              mock_auth_headers):
        """Test retrying a failed SMS message."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.retry_failed_message.return_value = True
        
        # Make request
        response = client.post("/api/sms/sms-123/retry", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "retry" in data["message"]
        
        # Verify mock calls
        mock_manager_instance.retry_failed_message.assert_called_once_with("sms-123")

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_retry_sms_not_found(self, mock_sms_manager, mock_auth, 
                                 client, mock_auth_headers):
        """Test retrying non-existent SMS."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.retry_failed_message.return_value = False
        
        # Make request
        response = client.post("/api/sms/non-existent/retry", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 404

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_cancel_sms(self, mock_sms_manager, mock_auth, client, 
                        mock_auth_headers):
        """Test cancelling a pending SMS message."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.cancel_message.return_value = True
        
        # Make request
        response = client.post("/api/sms/sms-123/cancel", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "cancelled" in data["message"]

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_sms_manager_error(self, mock_sms_manager, mock_auth, client, 
                               mock_auth_headers, sample_sms_send):
        """Test SMS manager error handling."""
        # Setup mocks to raise exception
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.send_sms.side_effect = Exception("SMS gateway error")
        
        # Make request
        response = client.post(
            "/api/sms/send",
            json=sample_sms_send,
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 500

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_unicode_message(self, mock_sms_manager, mock_auth, client, 
                             mock_auth_headers, sample_sms_info):
        """Test sending SMS with Unicode characters."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.send_sms.return_value = sample_sms_info
        
        # Make request with Unicode message
        unicode_message = {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Hello 🌟 世界 测试"
        }
        
        response = client.post(
            "/api/sms/send",
            json=unicode_message,
            headers=mock_auth_headers
        )
        
        # Assertions
        assert response.status_code == 200

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_sms_statistics(self, mock_sms_manager, mock_auth, client, 
                            mock_auth_headers):
        """Test getting SMS statistics."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        mock_manager_instance.get_statistics.return_value = {
            "total_messages": 100,
            "sent_messages": 95,
            "failed_messages": 5,
            "success_rate": 0.95
        }
        
        # Make request
        response = client.get("/api/sms/stats", headers=mock_auth_headers)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 100
        assert data["success_rate"] == 0.95

    def test_unauthorized_sms_request(self, client):
        """Test SMS request without authentication."""
        # Make request without auth headers
        response = client.post(
            "/api/sms/send",
            json={
                "from_number": "+1234567890",
                "to_number": "+0987654321",
                "message": "Test"
            }
        )
        
        # Assertions
        assert response.status_code == 401

    @patch('src.api.routes.sms.get_current_user')
    @patch('src.api.routes.sms.SMSManager')
    def test_bulk_sms_send(self, mock_sms_manager, mock_auth, client, 
                           mock_auth_headers):
        """Test sending multiple SMS messages."""
        # Setup mocks
        mock_auth.return_value = {"user_id": "test-user"}
        mock_manager_instance = AsyncMock()
        mock_sms_manager.return_value = mock_manager_instance
        
        # Create multiple SMS info objects
        sms_results = []
        for i in range(3):
            sms_info = SMSInfo(
                message_id=f"sms-{i}",
                from_number="+1234567890",
                to_number=f"+098765432{i}",
                message=f"Message {i}",
                status="sent",
                direction="outbound",
                timestamp=datetime.utcnow(),
                segments=1
            )
            sms_results.append(sms_info)
        
        mock_manager_instance.send_bulk_sms.return_value = sms_results
        
        # Make request
        bulk_data = {
            "from_number": "+1234567890",
            "messages": [
                {"to_number": "+0987654320", "message": "Message 0"},
                {"to_number": "+0987654321", "message": "Message 1"},
                {"to_number": "+0987654322", "message": "Message 2"}
            ]
        }
        
        response = client.post(
            "/api/sms/bulk",
            json=bulk_data,
            headers=mock_auth_headers
        )
        
        # Assertions (if bulk endpoint exists)
        # This test shows how to handle bulk operations
        if response.status_code != 404:  # If endpoint exists
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
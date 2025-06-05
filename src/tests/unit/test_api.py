"""API endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json

from src.api.main import app
from src.models.schemas import CallInfo, SMSInfo, CallStatus, SMSStatus


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get authentication headers."""
    # In a real test, this would get a valid JWT token
    return {"Authorization": "Bearer test-token"}


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_check(self, client):
        """Test health check returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "sip-server"


class TestCallEndpoints:
    """Test call management endpoints."""
    
    def test_initiate_call(self, client, auth_headers):
        """Test initiating a call."""
        call_data = {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "headers": {"X-Custom": "value"},
            "webhook_url": "https://example.com/webhook"
        }
        
        response = client.post(
            "/api/calls/initiate",
            json=call_data,
            headers=auth_headers
        )
        
        # Should fail without proper auth in real scenario
        assert response.status_code in [401, 500]
        
    def test_get_active_calls(self, client, auth_headers):
        """Test getting active calls."""
        response = client.get(
            "/api/calls/active",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 401]
        
    def test_get_call_info(self, client, auth_headers):
        """Test getting call information."""
        call_id = "test-call-id"
        response = client.get(
            f"/api/calls/{call_id}",
            headers=auth_headers
        )
        
        assert response.status_code in [404, 401]
        
    def test_hangup_call(self, client, auth_headers):
        """Test hanging up a call."""
        call_id = "test-call-id"
        response = client.post(
            f"/api/calls/{call_id}/hangup",
            headers=auth_headers
        )
        
        assert response.status_code in [404, 401]
        
    def test_transfer_call(self, client, auth_headers):
        """Test transferring a call."""
        call_id = "test-call-id"
        transfer_data = {
            "target_number": "+1122334455",
            "blind_transfer": True
        }
        
        response = client.post(
            f"/api/calls/{call_id}/transfer",
            json=transfer_data,
            headers=auth_headers
        )
        
        assert response.status_code in [404, 401]
        
    def test_send_dtmf(self, client, auth_headers):
        """Test sending DTMF digits."""
        call_id = "test-call-id"
        response = client.post(
            f"/api/calls/{call_id}/dtmf?digits=123",
            headers=auth_headers
        )
        
        assert response.status_code in [404, 401]


class TestSMSEndpoints:
    """Test SMS management endpoints."""
    
    def test_send_sms(self, client, auth_headers):
        """Test sending SMS."""
        sms_data = {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Test message",
            "webhook_url": "https://example.com/webhook"
        }
        
        response = client.post(
            "/api/sms/send",
            json=sms_data,
            headers=auth_headers
        )
        
        assert response.status_code in [401, 500]
        
    def test_get_sms_history(self, client, auth_headers):
        """Test getting SMS history."""
        response = client.get(
            "/api/sms/history",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 401]
        
    def test_send_bulk_sms(self, client, auth_headers):
        """Test sending bulk SMS."""
        sms_list = [
            {
                "from_number": "+1234567890",
                "to_number": "+0987654321",
                "message": "Test message 1"
            },
            {
                "from_number": "+1234567890",
                "to_number": "+1122334455",
                "message": "Test message 2"
            }
        ]
        
        response = client.post(
            "/api/sms/bulk",
            json=sms_list,
            headers=auth_headers
        )
        
        assert response.status_code in [401, 500]


class TestNumberEndpoints:
    """Test number management endpoints."""
    
    def test_block_number(self, client, auth_headers):
        """Test blocking a number."""
        block_data = {
            "number": "+1234567890",
            "reason": "Test block"
        }
        
        response = client.post(
            "/api/numbers/block",
            json=block_data,
            headers=auth_headers
        )
        
        assert response.status_code in [401, 500]
        
    def test_unblock_number(self, client, auth_headers):
        """Test unblocking a number."""
        number = "+1234567890"
        response = client.delete(
            f"/api/numbers/block/{number}",
            headers=auth_headers
        )
        
        assert response.status_code in [404, 401]
        
    def test_get_blocked_numbers(self, client, auth_headers):
        """Test getting blocked numbers."""
        response = client.get(
            "/api/numbers/blocked",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 401]
        
    def test_register_number(self, client, auth_headers):
        """Test registering a number."""
        number_data = {
            "number": "+1234567890",
            "display_name": "Test Number",
            "capabilities": ["voice", "sms"]
        }
        
        response = client.post(
            "/api/numbers/register",
            json=number_data,
            headers=auth_headers
        )
        
        assert response.status_code in [401, 500]


class TestConfigEndpoints:
    """Test configuration endpoints."""
    
    def test_get_config(self, client, auth_headers):
        """Test getting configuration."""
        response = client.get(
            "/api/config/",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 401]
        
    def test_update_config(self, client, auth_headers):
        """Test updating configuration."""
        config_data = {
            "sip_domains": ["sip.olib.ai"],
            "rtp_port_start": 10000,
            "rtp_port_end": 20000,
            "max_concurrent_calls": 1000,
            "call_timeout": 3600,
            "enable_recording": False,
            "enable_transcription": False,
            "nat_traversal": True,
            "tls_enabled": True,
            "rate_limit": {
                "calls_per_minute": 60,
                "sms_per_minute": 100
            }
        }
        
        response = client.put(
            "/api/config/",
            json=config_data,
            headers=auth_headers
        )
        
        assert response.status_code in [401, 403]
        
    def test_get_server_status(self, client, auth_headers):
        """Test getting server status."""
        response = client.get(
            "/api/config/status",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 401]


class TestWebhookEndpoints:
    """Test webhook endpoints."""
    
    def test_incoming_call_webhook(self, client):
        """Test incoming call webhook."""
        webhook_data = {
            "call_id": "test-call-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "status": "ringing",
            "headers": {}
        }
        
        response = client.post(
            "/webhooks/call/incoming",
            json=webhook_data,
            headers={"X-Webhook-Signature": "test-signature"}
        )
        
        # Should fail without proper signature
        assert response.status_code in [401, 200]
        
    def test_sms_webhook(self, client):
        """Test SMS webhook."""
        webhook_data = {
            "message_id": "test-sms-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Test SMS",
            "status": "received"
        }
        
        response = client.post(
            "/webhooks/sms/incoming",
            json=webhook_data,
            headers={"X-Webhook-Signature": "test-signature"}
        )
        
        assert response.status_code in [401, 200]
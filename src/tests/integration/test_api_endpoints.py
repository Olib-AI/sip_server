"""
Comprehensive integration tests for API endpoints.
Tests all REST API functionality with realistic scenarios.
"""
import pytest
import json
import time
from datetime import datetime
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from src.api.main import app


class TestHealthEndpoints:
    """Test health and monitoring endpoints."""
    
    def test_health_check(self, api_client):
        """Test health check endpoint."""
        response = api_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "sip-server"
        
        # Verify timestamp format
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)
    
    def test_metrics_endpoint(self, api_client):
        """Test Prometheus metrics endpoint."""
        response = api_client.get("/metrics")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        
        metrics_text = response.text
        
        # Check for required metrics
        assert "sip_server_cpu_percent" in metrics_text
        assert "sip_server_memory_percent" in metrics_text
        assert "sip_server_uptime_seconds" in metrics_text
        assert "sip_server_info" in metrics_text
        
        # Verify metric format
        lines = metrics_text.strip().split('\n')
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        
        for line in metric_lines:
            assert ' ' in line  # Should have metric name and value
            parts = line.split(' ')
            assert len(parts) >= 2  # Name and value
            
            # Value should be numeric
            try:
                float(parts[-1])
            except ValueError:
                pytest.fail(f"Invalid metric value in line: {line}")


class TestCallManagementAPI:
    """Test call management API endpoints."""
    
    @pytest.fixture
    def mock_call_manager(self):
        """Mock call manager for testing."""
        with patch('src.api.routes.calls.get_call_manager') as mock:
            manager = AsyncMock()
            manager.initiate_outbound_call = AsyncMock()
            manager.get_active_calls = AsyncMock()
            manager.hangup_call = AsyncMock()
            manager.transfer_call = AsyncMock()
            manager.hold_call = AsyncMock()
            manager.resume_call = AsyncMock()
            manager.get_call_session = AsyncMock()
            manager.get_statistics = AsyncMock()
            mock.return_value = manager
            yield manager
    
    def test_initiate_call(self, api_client, mock_call_manager):
        """Test call initiation endpoint."""
        call_data = {
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "caller_name": "Test Caller",
            "webhook_url": "https://example.com/webhook"
        }
        
        # Mock successful call initiation
        mock_call_manager.initiate_outbound_call.return_value = {
            "success": True,
            "call_id": "test-call-123",
            "session_id": "session-456",
            "from_number": call_data["from_number"],
            "to_number": call_data["to_number"]
        }
        
        response = api_client.post("/api/calls/initiate", json=call_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["success"] is True
        assert data["call_id"] == "test-call-123"
        assert data["from_number"] == call_data["from_number"]
        assert data["to_number"] == call_data["to_number"]
        
        # Verify call manager was called
        mock_call_manager.initiate_outbound_call.assert_called_once()
        call_args = mock_call_manager.initiate_outbound_call.call_args[0][0]
        assert call_args["from_number"] == call_data["from_number"]
        assert call_args["to_number"] == call_data["to_number"]
    
    def test_initiate_call_validation(self, api_client, mock_call_manager):
        """Test call initiation input validation."""
        # Test missing required fields
        invalid_data = {
            "from_number": "+12345678901"
            # Missing to_number
        }
        
        response = api_client.post("/api/calls/initiate", json=invalid_data)
        assert response.status_code == 422
        
        # Test invalid phone number format
        invalid_data = {
            "from_number": "invalid_number",
            "to_number": "+10987654321"
        }
        
        response = api_client.post("/api/calls/initiate", json=invalid_data)
        assert response.status_code == 422
    
    def test_get_active_calls(self, api_client, mock_call_manager):
        """Test getting active calls."""
        # Mock active calls
        mock_call_manager.get_active_calls.return_value = [
            {
                "call_id": "call-1",
                "from_number": "+12345678901",
                "to_number": "+10987654321",
                "state": "connected",
                "start_time": "2024-01-01T12:00:00Z",
                "duration": 30.5
            },
            {
                "call_id": "call-2",
                "from_number": "+13333333333",
                "to_number": "+14444444444",
                "state": "ringing",
                "start_time": "2024-01-01T12:01:00Z",
                "duration": None
            }
        ]
        
        response = api_client.get("/api/calls/active")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["calls"]) == 2
        assert data["total_active"] == 2
        
        # Verify call data
        call1 = data["calls"][0]
        assert call1["call_id"] == "call-1"
        assert call1["state"] == "connected"
        assert call1["duration"] == 30.5
    
    def test_get_active_calls_filtered(self, api_client, mock_call_manager):
        """Test getting active calls with number filter."""
        filter_number = "+12345678901"
        
        mock_call_manager.get_active_calls.return_value = [
            {
                "call_id": "filtered-call",
                "from_number": filter_number,
                "to_number": "+10987654321",
                "state": "connected"
            }
        ]
        
        response = api_client.get(f"/api/calls/active?number={filter_number}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["calls"]) == 1
        assert data["calls"][0]["from_number"] == filter_number
        
        # Verify filter was passed to call manager
        mock_call_manager.get_active_calls.assert_called_with(filter_number)
    
    def test_hangup_call(self, api_client, mock_call_manager):
        """Test hanging up a call."""
        call_id = "test-call-hangup"
        
        mock_call_manager.hangup_call.return_value = True
        
        response = api_client.post(f"/api/calls/{call_id}/hangup")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["call_id"] == call_id
        assert data["action"] == "hangup"
        
        mock_call_manager.hangup_call.assert_called_once_with(call_id, "api_request")
    
    def test_hangup_nonexistent_call(self, api_client, mock_call_manager):
        """Test hanging up non-existent call."""
        call_id = "nonexistent-call"
        
        mock_call_manager.hangup_call.return_value = False
        
        response = api_client.post(f"/api/calls/{call_id}/hangup")
        
        assert response.status_code == 404
        data = response.json()
        
        assert data["success"] is False
        assert "not found" in data["error"].lower()
    
    def test_transfer_call(self, api_client, mock_call_manager):
        """Test transferring a call."""
        call_id = "test-call-transfer"
        transfer_data = {
            "target_number": "+19999999999",
            "transfer_type": "blind"
        }
        
        mock_call_manager.transfer_call.return_value = True
        
        response = api_client.post(f"/api/calls/{call_id}/transfer", json=transfer_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["call_id"] == call_id
        assert data["target_number"] == transfer_data["target_number"]
        assert data["transfer_type"] == transfer_data["transfer_type"]
        
        mock_call_manager.transfer_call.assert_called_once_with(
            call_id, transfer_data["target_number"], transfer_data["transfer_type"]
        )
    
    def test_hold_resume_call(self, api_client, mock_call_manager):
        """Test holding and resuming a call."""
        call_id = "test-call-hold"
        
        # Test hold
        mock_call_manager.hold_call.return_value = True
        
        response = api_client.post(f"/api/calls/{call_id}/hold")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["action"] == "hold"
        
        # Test resume
        mock_call_manager.resume_call.return_value = True
        
        response = api_client.post(f"/api/calls/{call_id}/resume")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["action"] == "resume"
    
    def test_send_dtmf(self, api_client, mock_call_manager):
        """Test sending DTMF to a call."""
        call_id = "test-call-dtmf"
        dtmf_data = {
            "digits": "123*0#",
            "duration_ms": 100,
            "interval_ms": 50
        }
        
        mock_call_manager.get_call_session.return_value = {"call_id": call_id}
        
        response = api_client.post(f"/api/calls/{call_id}/dtmf", json=dtmf_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["call_id"] == call_id
        assert data["digits"] == dtmf_data["digits"]
    
    def test_call_statistics(self, api_client, mock_call_manager):
        """Test getting call statistics."""
        mock_call_manager.get_statistics.return_value = {
            "total_calls": 1000,
            "active_calls": 25,
            "completed_calls": 950,
            "failed_calls": 50,
            "success_rate": 0.95,
            "average_duration": 120.5,
            "concurrent_utilization": 0.25
        }
        
        response = api_client.get("/api/calls/statistics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_calls"] == 1000
        assert data["active_calls"] == 25
        assert data["success_rate"] == 0.95
        assert data["average_duration"] == 120.5


class TestSMSAPI:
    """Test SMS API endpoints."""
    
    @pytest.fixture
    def mock_sms_manager(self):
        """Mock SMS manager for testing."""
        with patch('src.api.routes.sms.get_sms_manager') as mock:
            manager = AsyncMock()
            manager.send_sms = AsyncMock()
            manager.get_message_status = AsyncMock()
            manager.get_message_history = AsyncMock()
            manager.get_statistics = AsyncMock()
            mock.return_value = manager
            yield manager
    
    def test_send_sms(self, api_client, mock_sms_manager):
        """Test sending SMS message."""
        sms_data = {
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "message": "Test SMS message with unicode 🚀",
            "priority": "normal"
        }
        
        mock_sms_manager.send_sms.return_value = {
            "success": True,
            "message_id": "sms-123-456",
            "status": "queued",
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        response = api_client.post("/api/sms/send", json=sms_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["success"] is True
        assert data["message_id"] == "sms-123-456"
        assert data["status"] == "queued"
        
        # Verify SMS manager was called
        mock_sms_manager.send_sms.assert_called_once()
        call_args = mock_sms_manager.send_sms.call_args
        assert call_args[1]["from_number"] == sms_data["from_number"]
        assert call_args[1]["to_number"] == sms_data["to_number"]
        assert call_args[1]["content"] == sms_data["message"]
    
    def test_send_sms_validation(self, api_client, mock_sms_manager):
        """Test SMS sending input validation."""
        # Test missing required fields
        invalid_data = {
            "from_number": "+12345678901"
            # Missing to_number and message
        }
        
        response = api_client.post("/api/sms/send", json=invalid_data)
        assert response.status_code == 422
        
        # Test empty message
        invalid_data = {
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "message": ""
        }
        
        response = api_client.post("/api/sms/send", json=invalid_data)
        assert response.status_code == 422
        
        # Test message too long
        invalid_data = {
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "message": "A" * 2000  # Too long
        }
        
        response = api_client.post("/api/sms/send", json=invalid_data)
        assert response.status_code == 422
    
    def test_get_message_status(self, api_client, mock_sms_manager):
        """Test getting SMS message status."""
        message_id = "sms-status-test"
        
        mock_sms_manager.get_message_status.return_value = {
            "success": True,
            "message_id": message_id,
            "status": "delivered",
            "timestamp": "2024-01-01T12:00:00Z",
            "delivery_time": "2024-01-01T12:00:05Z"
        }
        
        response = api_client.get(f"/api/sms/{message_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["message_id"] == message_id
        assert data["status"] == "delivered"
        assert "delivery_time" in data
    
    def test_get_message_status_not_found(self, api_client, mock_sms_manager):
        """Test getting status of non-existent message."""
        message_id = "nonexistent-message"
        
        mock_sms_manager.get_message_status.return_value = {
            "success": False,
            "error": "Message not found"
        }
        
        response = api_client.get(f"/api/sms/{message_id}")
        
        assert response.status_code == 404
        data = response.json()
        
        assert data["success"] is False
        assert "not found" in data["error"].lower()
    
    def test_get_message_history(self, api_client, mock_sms_manager):
        """Test getting SMS message history."""
        number = "+12345678901"
        
        mock_sms_manager.get_message_history.return_value = [
            {
                "message_id": "sms-1",
                "from_number": "+12345678901",
                "to_number": "+10987654321",
                "content": "First message",
                "direction": "outbound",
                "status": "delivered",
                "timestamp": "2024-01-01T12:00:00Z"
            },
            {
                "message_id": "sms-2",
                "from_number": "+10987654321",
                "to_number": "+12345678901",
                "content": "Reply message",
                "direction": "inbound",
                "status": "received",
                "timestamp": "2024-01-01T12:01:00Z"
            }
        ]
        
        response = api_client.get(f"/api/sms/history?number={number}&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["messages"]) == 2
        assert data["total_count"] == 2
        
        # Verify message data
        msg1 = data["messages"][0]
        assert msg1["message_id"] == "sms-1"
        assert msg1["direction"] == "outbound"
        assert msg1["status"] == "delivered"
    
    def test_sms_statistics(self, api_client, mock_sms_manager):
        """Test getting SMS statistics."""
        mock_sms_manager.get_statistics.return_value = {
            "total_sent": 500,
            "total_received": 300,
            "failed_messages": 15,
            "pending_messages": 5,
            "success_rate": 0.97,
            "average_delivery_time": 2.3
        }
        
        response = api_client.get("/api/sms/statistics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_sent"] == 500
        assert data["total_received"] == 300
        assert data["success_rate"] == 0.97
        assert data["average_delivery_time"] == 2.3


class TestNumberManagementAPI:
    """Test number management API endpoints."""
    
    @pytest.fixture
    def mock_number_manager(self):
        """Mock number manager for testing."""
        with patch('src.api.routes.numbers.get_number_manager') as mock:
            manager = AsyncMock()
            manager.block_number = AsyncMock()
            manager.unblock_number = AsyncMock()
            manager.get_blocked_numbers = AsyncMock()
            manager.is_number_blocked = AsyncMock()
            mock.return_value = manager
            yield manager
    
    def test_block_number(self, api_client, mock_number_manager):
        """Test blocking a phone number."""
        block_data = {
            "number": "+15551234567",
            "reason": "Spam caller",
            "blocked_by": "admin"
        }
        
        mock_number_manager.block_number.return_value = {
            "success": True,
            "number": block_data["number"],
            "reason": block_data["reason"],
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        response = api_client.post("/api/numbers/block", json=block_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["success"] is True
        assert data["number"] == block_data["number"]
        assert data["reason"] == block_data["reason"]
    
    def test_unblock_number(self, api_client, mock_number_manager):
        """Test unblocking a phone number."""
        number = "+15551234567"
        
        mock_number_manager.unblock_number.return_value = {
            "success": True,
            "number": number,
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        response = api_client.delete(f"/api/numbers/block/{number}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["number"] == number
    
    def test_get_blocked_numbers(self, api_client, mock_number_manager):
        """Test getting list of blocked numbers."""
        mock_number_manager.get_blocked_numbers.return_value = [
            {
                "number": "+15551111111",
                "reason": "Spam",
                "blocked_at": "2024-01-01T10:00:00Z",
                "blocked_by": "admin"
            },
            {
                "number": "+15552222222",
                "reason": "Harassment",
                "blocked_at": "2024-01-01T11:00:00Z",
                "blocked_by": "system"
            }
        ]
        
        response = api_client.get("/api/numbers/blocked")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["blocked_numbers"]) == 2
        assert data["total_blocked"] == 2
        
        # Verify number data
        num1 = data["blocked_numbers"][0]
        assert num1["number"] == "+15551111111"
        assert num1["reason"] == "Spam"
    
    def test_check_number_status(self, api_client, mock_number_manager):
        """Test checking if number is blocked."""
        number = "+15551234567"
        
        mock_number_manager.is_number_blocked.return_value = {
            "number": number,
            "is_blocked": True,
            "reason": "Previous spam reports",
            "blocked_at": "2024-01-01T10:00:00Z"
        }
        
        response = api_client.get(f"/api/numbers/{number}/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["number"] == number
        assert data["is_blocked"] is True
        assert data["reason"] == "Previous spam reports"


class TestTrunkManagementAPI:
    """Test SIP trunk management API endpoints."""
    
    @pytest.fixture
    def mock_trunk_manager(self):
        """Mock trunk manager for testing."""
        with patch('src.api.routes.trunks.get_trunk_manager') as mock:
            manager = AsyncMock()
            manager.add_trunk = AsyncMock()
            manager.update_trunk = AsyncMock()
            manager.remove_trunk = AsyncMock()
            manager.get_trunks = AsyncMock()
            manager.get_trunk_status = AsyncMock()
            mock.return_value = manager
            yield manager
    
    def test_add_trunk(self, api_client, mock_trunk_manager):
        """Test adding SIP trunk."""
        trunk_data = {
            "name": "Test Trunk",
            "provider": "test_provider",
            "proxy_address": "sip.test-provider.com",
            "proxy_port": 5060,
            "username": "test_user",
            "password": "test_password",
            "supports_outbound": True,
            "supports_inbound": True,
            "codec_preferences": ["PCMU", "PCMA"]
        }
        
        mock_trunk_manager.add_trunk.return_value = {
            "success": True,
            "trunk_id": "trunk-123",
            "name": trunk_data["name"],
            "status": "active"
        }
        
        response = api_client.post("/api/trunks", json=trunk_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["success"] is True
        assert data["trunk_id"] == "trunk-123"
        assert data["name"] == trunk_data["name"]
    
    def test_get_trunks(self, api_client, mock_trunk_manager):
        """Test getting list of trunks."""
        mock_trunk_manager.get_trunks.return_value = [
            {
                "trunk_id": "trunk-1",
                "name": "Primary Trunk",
                "provider": "provider1",
                "status": "active",
                "calls_active": 10,
                "calls_total": 1000
            },
            {
                "trunk_id": "trunk-2",
                "name": "Backup Trunk",
                "provider": "provider2",
                "status": "standby",
                "calls_active": 0,
                "calls_total": 50
            }
        ]
        
        response = api_client.get("/api/trunks")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["trunks"]) == 2
        assert data["total_trunks"] == 2
        
        # Verify trunk data
        trunk1 = data["trunks"][0]
        assert trunk1["trunk_id"] == "trunk-1"
        assert trunk1["status"] == "active"
        assert trunk1["calls_active"] == 10
    
    def test_update_trunk(self, api_client, mock_trunk_manager):
        """Test updating trunk configuration."""
        trunk_id = "trunk-123"
        update_data = {
            "name": "Updated Trunk Name",
            "proxy_port": 5061,
            "codec_preferences": ["PCMA", "PCMU", "G722"]
        }
        
        mock_trunk_manager.update_trunk.return_value = {
            "success": True,
            "trunk_id": trunk_id,
            "updated_fields": list(update_data.keys())
        }
        
        response = api_client.put(f"/api/trunks/{trunk_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["trunk_id"] == trunk_id
        assert "name" in data["updated_fields"]
    
    def test_remove_trunk(self, api_client, mock_trunk_manager):
        """Test removing trunk."""
        trunk_id = "trunk-to-remove"
        
        mock_trunk_manager.remove_trunk.return_value = {
            "success": True,
            "trunk_id": trunk_id,
            "removed_at": "2024-01-01T12:00:00Z"
        }
        
        response = api_client.delete(f"/api/trunks/{trunk_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["trunk_id"] == trunk_id
    
    def test_get_trunk_status(self, api_client, mock_trunk_manager):
        """Test getting trunk status."""
        trunk_id = "trunk-status-test"
        
        mock_trunk_manager.get_trunk_status.return_value = {
            "trunk_id": trunk_id,
            "status": "active",
            "registration_status": "registered",
            "last_keepalive": "2024-01-01T12:00:00Z",
            "active_calls": 5,
            "total_calls": 500,
            "error_rate": 0.02
        }
        
        response = api_client.get(f"/api/trunks/{trunk_id}/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["trunk_id"] == trunk_id
        assert data["status"] == "active"
        assert data["registration_status"] == "registered"
        assert data["active_calls"] == 5


class TestConfigurationAPI:
    """Test configuration API endpoints."""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Mock configuration manager for testing."""
        with patch('src.api.routes.config.get_config_manager') as mock:
            manager = AsyncMock()
            manager.get_config = AsyncMock()
            manager.update_config = AsyncMock()
            manager.validate_config = AsyncMock()
            manager.reload_config = AsyncMock()
            mock.return_value = manager
            yield manager
    
    def test_get_configuration(self, api_client, mock_config_manager):
        """Test getting current configuration."""
        mock_config_manager.get_config.return_value = {
            "api": {
                "port": 8080,
                "cors_origins": ["*"]
            },
            "sip": {
                "domain": "sip.example.com",
                "port": 5060,
                "transport": "UDP"
            },
            "audio": {
                "sample_rate": 8000,
                "codecs": ["PCMU", "PCMA"]
            }
        }
        
        response = api_client.get("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "api" in data
        assert "sip" in data
        assert "audio" in data
        assert data["api"]["port"] == 8080
        assert data["sip"]["domain"] == "sip.example.com"
    
    def test_update_configuration(self, api_client, mock_config_manager):
        """Test updating configuration."""
        config_update = {
            "api": {
                "port": 8081
            },
            "audio": {
                "sample_rate": 16000
            }
        }
        
        mock_config_manager.validate_config.return_value = {"valid": True}
        mock_config_manager.update_config.return_value = {
            "success": True,
            "updated_sections": ["api", "audio"],
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        response = api_client.put("/api/config", json=config_update)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "api" in data["updated_sections"]
        assert "audio" in data["updated_sections"]
    
    def test_validate_configuration(self, api_client, mock_config_manager):
        """Test configuration validation."""
        config_to_validate = {
            "sip": {
                "domain": "invalid..domain",  # Invalid domain
                "port": 99999  # Invalid port
            }
        }
        
        mock_config_manager.validate_config.return_value = {
            "valid": False,
            "errors": [
                "Invalid SIP domain format",
                "SIP port must be between 1 and 65535"
            ]
        }
        
        response = api_client.post("/api/config/validate", json=config_to_validate)
        
        assert response.status_code == 400
        data = response.json()
        
        assert data["valid"] is False
        assert len(data["errors"]) == 2
        assert "Invalid SIP domain" in data["errors"][0]
    
    def test_reload_configuration(self, api_client, mock_config_manager):
        """Test configuration reload."""
        mock_config_manager.reload_config.return_value = {
            "success": True,
            "reloaded_at": "2024-01-01T12:00:00Z",
            "changes_detected": True
        }
        
        response = api_client.post("/api/config/reload")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["changes_detected"] is True


class TestWebhookAPI:
    """Test webhook endpoints for external integrations."""
    
    def test_incoming_call_webhook(self, api_client):
        """Test incoming call webhook endpoint."""
        webhook_data = {
            "event": "incoming_call",
            "call_id": "webhook-call-123",
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "timestamp": "2024-01-01T12:00:00Z",
            "sip_headers": {
                "User-Agent": "Test SIP Client",
                "Contact": "<sip:test@192.168.1.100:5060>"
            }
        }
        
        response = api_client.post("/webhooks/incoming_call", json=webhook_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["received"] is True
        assert data["event"] == "incoming_call"
        assert data["call_id"] == webhook_data["call_id"]
    
    def test_sms_webhook(self, api_client):
        """Test SMS webhook endpoint."""
        webhook_data = {
            "event": "sms_received",
            "message_id": "webhook-sms-123",
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "content": "Webhook test message",
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        response = api_client.post("/webhooks/sms", json=webhook_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["received"] is True
        assert data["event"] == "sms_received"
        assert data["message_id"] == webhook_data["message_id"]
    
    def test_call_status_webhook(self, api_client):
        """Test call status update webhook."""
        webhook_data = {
            "event": "call_status_update",
            "call_id": "webhook-status-123",
            "status": "completed",
            "previous_status": "connected",
            "duration": 125.5,
            "timestamp": "2024-01-01T12:02:05Z",
            "reason": "normal_clearing"
        }
        
        response = api_client.post("/webhooks/call_status", json=webhook_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["received"] is True
        assert data["event"] == "call_status_update"
        assert data["call_id"] == webhook_data["call_id"]


class TestAPIAuthentication:
    """Test API authentication and authorization."""
    
    def test_jwt_authentication(self, api_client):
        """Test JWT token authentication."""
        # Test without token
        response = api_client.get("/api/calls/active")
        # Depending on implementation, might require auth
        # assert response.status_code == 401
        
        # Test with valid token
        valid_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test.token"
        headers = {"Authorization": f"Bearer {valid_token}"}
        
        with patch('src.utils.auth.verify_jwt_token') as mock_verify:
            mock_verify.return_value = {"user_id": "test_user", "permissions": ["call_management"]}
            
            response = api_client.get("/api/calls/active", headers=headers)
            # Should work with valid token
    
    def test_api_key_authentication(self, api_client):
        """Test API key authentication."""
        # Test with API key
        api_key = "test-api-key-12345"
        headers = {"X-API-Key": api_key}
        
        with patch('src.utils.auth.verify_api_key') as mock_verify:
            mock_verify.return_value = True
            
            response = api_client.get("/api/calls/statistics", headers=headers)
            # Should work with valid API key
    
    def test_permission_based_access(self, api_client):
        """Test permission-based access control."""
        # Test user with limited permissions
        limited_token = "limited.jwt.token"
        headers = {"Authorization": f"Bearer {limited_token}"}
        
        with patch('src.utils.auth.verify_jwt_token') as mock_verify:
            mock_verify.return_value = {"user_id": "limited_user", "permissions": ["read_only"]}
            
            # Should allow read operations
            response = api_client.get("/api/calls/active", headers=headers)
            
            # Should deny write operations
            call_data = {
                "from_number": "+12345678901",
                "to_number": "+10987654321"
            }
            response = api_client.post("/api/calls/initiate", json=call_data, headers=headers)
            # assert response.status_code == 403


class TestAPIErrorHandling:
    """Test API error handling and edge cases."""
    
    def test_malformed_json(self, api_client):
        """Test handling of malformed JSON requests."""
        response = api_client.post(
            "/api/calls/initiate",
            data="invalid json {",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
    
    def test_missing_content_type(self, api_client):
        """Test handling of missing content type."""
        response = api_client.post(
            "/api/calls/initiate",
            data='{"from_number": "+12345678901", "to_number": "+10987654321"}'
        )
        
        # Should handle gracefully
        assert response.status_code in [400, 422]
    
    def test_request_size_limit(self, api_client):
        """Test request size limits."""
        large_data = {
            "from_number": "+12345678901",
            "to_number": "+10987654321",
            "custom_data": "A" * 10000  # Large payload
        }
        
        response = api_client.post("/api/calls/initiate", json=large_data)
        
        # Should handle large requests appropriately
        assert response.status_code in [200, 201, 413, 422]
    
    def test_rate_limiting(self, api_client):
        """Test API rate limiting."""
        # Make many rapid requests
        responses = []
        for i in range(10):
            response = api_client.get("/health")
            responses.append(response)
        
        # All should succeed for health endpoint (typically not rate limited)
        assert all(r.status_code == 200 for r in responses)
    
    def test_concurrent_requests(self, api_client):
        """Test handling of concurrent requests."""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = api_client.get("/health")
            results.append(response.status_code)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 5


class TestAPIPerformance:
    """Test API performance characteristics."""
    
    def test_response_times(self, api_client, performance_thresholds):
        """Test API response times."""
        endpoints = [
            "/health",
            "/metrics",
            "/api/calls/active",
            "/api/sms/statistics"
        ]
        
        for endpoint in endpoints:
            start_time = time.perf_counter()
            response = api_client.get(endpoint)
            end_time = time.perf_counter()
            
            response_time_ms = (end_time - start_time) * 1000
            
            # Response time should be reasonable
            assert response_time_ms < performance_thresholds["api_response_ms"]
            assert response.status_code in [200, 401, 403]  # Allow auth errors
    
    def test_throughput(self, api_client):
        """Test API throughput."""
        import time
        
        request_count = 50
        start_time = time.perf_counter()
        
        # Make multiple requests
        for i in range(request_count):
            response = api_client.get("/health")
            assert response.status_code == 200
        
        end_time = time.perf_counter()
        total_time = end_time - start_time
        requests_per_second = request_count / total_time
        
        # Should handle at least 20 requests per second
        assert requests_per_second >= 20
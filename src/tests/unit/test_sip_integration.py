"""Unit tests for new SIP integration modules."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from fastapi.testclient import TestClient
from datetime import datetime
import json

from src.api.sip_integration import app, initialize_services
from src.call_handling.call_manager import CallManager, CallSession, CallState, CallDirection
from src.call_handling.websocket_integration import WebSocketCallBridge
from src.main_integration import SIPIntegrationServer


class TestSIPIntegrationAPI:
    """Test suite for SIP integration API."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_call_manager(self):
        """Mock call manager."""
        return AsyncMock(spec=CallManager)
    
    @pytest.fixture
    def mock_websocket_bridge(self):
        """Mock WebSocket bridge."""
        return AsyncMock(spec=WebSocketCallBridge)
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
    
    @patch('src.api.sip_integration.call_manager')
    @patch('src.api.sip_integration.websocket_bridge')
    def test_incoming_call_notification(self, mock_bridge, mock_manager, client):
        """Test incoming call notification endpoint."""
        # Setup mocks
        mock_manager.return_value = Mock()
        mock_bridge.notify_incoming_call = AsyncMock(return_value={
            "action": "accept",
            "code": 200,
            "reason": "OK"
        })
        initialize_services(mock_manager, mock_bridge)
        
        # Test data
        call_data = {
            "type": "invite",
            "call_id": "test-call-123",
            "from": "+1234567890",
            "to": "+0987654321",
            "source_ip": "192.168.1.100"
        }
        
        # Make request
        response = client.post("/api/sip/calls/incoming", json=call_data)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["call_id"] == "test-call-123"
        assert data["action"] == "accept"
    
    @patch('src.api.sip_integration.websocket_bridge')
    def test_incoming_sms_notification(self, mock_bridge, client):
        """Test incoming SMS notification endpoint."""
        # Setup mocks
        mock_bridge.handle_sip_message = AsyncMock(return_value={
            "success": True,
            "message": "SMS processed"
        })
        initialize_services(None, mock_bridge)
        
        # Test data
        sms_data = {
            "type": "sms",
            "from": "+1234567890",
            "to": "+0987654321",
            "body": "Test message"
        }
        
        # Make request
        response = client.post("/api/sip/sms/incoming", json=sms_data)
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["message"] == "SMS processed"
    
    @patch('src.api.sip_integration.call_manager')
    def test_get_active_calls(self, mock_manager, client):
        """Test get active calls endpoint."""
        # Setup mock
        mock_call = Mock()
        mock_call.call_id = "test-call-123"
        mock_call.session_id = "session-456"
        mock_call.caller.number = "+1234567890"
        mock_call.callee.number = "+0987654321"
        mock_call.direction.value = "inbound"
        mock_call.state.value = "connected"
        mock_call.duration.return_value = 120.5
        mock_call.created_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_call.is_recording = False
        mock_call.is_on_hold = False
        
        mock_manager.get_active_calls.return_value = [mock_call]
        initialize_services(mock_manager, None)
        
        # Make request
        response = client.get("/api/sip/calls/active")
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert len(data["calls"]) == 1
        assert data["calls"][0]["call_id"] == "test-call-123"
        assert data["calls"][0]["duration"] == 120.5
    
    def test_invalid_incoming_call_data(self, client):
        """Test incoming call with invalid data."""
        # Missing required fields
        invalid_data = {
            "type": "invite",
            "from": "+1234567890"
            # missing "to", "call_id"
        }
        
        response = client.post("/api/sip/calls/incoming", json=invalid_data)
        assert response.status_code == 400
    
    def test_invalid_json(self, client):
        """Test with invalid JSON."""
        response = client.post(
            "/api/sip/calls/incoming",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400


class TestCallManager:
    """Test suite for call manager."""
    
    @pytest.fixture
    def call_manager(self):
        """Create call manager instance."""
        return CallManager(max_concurrent_calls=10)
    
    @pytest.fixture
    def sample_sip_data(self):
        """Sample SIP call data."""
        return {
            "call_id": "test-call-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "sip_call_id": "test-call-123",
            "remote_ip": "192.168.1.100"
        }
    
    @pytest.mark.asyncio
    async def test_handle_incoming_call(self, call_manager, sample_sip_data):
        """Test handling incoming call."""
        result = await call_manager.handle_incoming_call(sample_sip_data)
        
        assert result["action"] == "accept"
        assert "call_id" in result
        assert "session_id" in result
    
    @pytest.mark.asyncio
    async def test_initiate_outbound_call(self, call_manager):
        """Test initiating outbound call."""
        call_data = {
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        result = await call_manager.initiate_outbound_call(call_data)
        
        assert result["success"] == True
        assert "call_id" in result
        assert result["from_number"] == "+1234567890"
        assert result["to_number"] == "+0987654321"
    
    @pytest.mark.asyncio
    async def test_update_call_state(self, call_manager, sample_sip_data):
        """Test updating call state."""
        # First create a call
        result = await call_manager.handle_incoming_call(sample_sip_data)
        call_id = result["call_id"]
        
        # Update state
        success = await call_manager.update_call_state(call_id, CallState.CONNECTED)
        assert success == True
        
        # Verify state
        call_session = call_manager.get_call_session(call_id)
        assert call_session.state == CallState.CONNECTED
    
    @pytest.mark.asyncio
    async def test_hangup_call(self, call_manager, sample_sip_data):
        """Test hanging up call."""
        # First create a call
        result = await call_manager.handle_incoming_call(sample_sip_data)
        call_id = result["call_id"]
        
        # Hangup call
        success = await call_manager.hangup_call(call_id)
        assert success == True
        
        # Verify state
        call_session = call_manager.get_call_session(call_id)
        assert call_session.state == CallState.COMPLETED
    
    def test_get_statistics(self, call_manager):
        """Test getting call statistics."""
        stats = call_manager.get_statistics()
        
        assert "uptime_seconds" in stats
        assert "total_calls" in stats
        assert "active_calls" in stats
        assert "success_rate" in stats
    
    @pytest.mark.asyncio
    async def test_concurrent_call_limit(self, sample_sip_data):
        """Test concurrent call limits."""
        # Create manager with low limit
        call_manager = CallManager(max_concurrent_calls=1)
        
        # First call should succeed
        result1 = await call_manager.handle_incoming_call(sample_sip_data)
        assert result1["action"] == "accept"
        
        # Second call should be rejected due to limit
        sip_data2 = sample_sip_data.copy()
        sip_data2["call_id"] = "test-call-456"
        result2 = await call_manager.handle_incoming_call(sip_data2)
        assert result2["action"] == "reject"
        assert result2["code"] == 486  # Busy Here


class TestWebSocketBridge:
    """Test suite for WebSocket bridge."""
    
    @pytest.fixture
    def call_manager(self):
        """Mock call manager."""
        return AsyncMock(spec=CallManager)
    
    @pytest.fixture
    def websocket_bridge(self, call_manager):
        """Create WebSocket bridge instance."""
        return WebSocketCallBridge(call_manager)
    
    @pytest.mark.asyncio
    async def test_notify_incoming_call(self, websocket_bridge, call_manager):
        """Test notifying about incoming call."""
        call_manager.handle_incoming_call.return_value = {
            "action": "accept",
            "call_id": "test-call-123"
        }
        
        sip_data = {
            "call_id": "test-call-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        result = await websocket_bridge.notify_incoming_call(sip_data)
        
        assert result["action"] == "accept"
        call_manager.handle_incoming_call.assert_called_once_with(sip_data)
    
    @pytest.mark.asyncio
    async def test_handle_sip_message(self, websocket_bridge):
        """Test handling SIP message."""
        sms_data = {
            "from": "+1234567890",
            "to": "+0987654321",
            "body": "Test message"
        }
        
        result = await websocket_bridge.handle_sip_message(sms_data)
        
        assert result["success"] == True
    
    def test_get_statistics(self, websocket_bridge):
        """Test getting bridge statistics."""
        stats = websocket_bridge.get_statistics()
        
        assert "active_connections" in stats
        assert "call_mappings" in stats
        assert "rtp_sessions" in stats


class TestSIPIntegrationServer:
    """Test suite for main integration server."""
    
    @pytest.fixture
    def integration_server(self):
        """Create integration server instance."""
        return SIPIntegrationServer()
    
    def test_load_default_config(self, integration_server):
        """Test loading default configuration."""
        config = integration_server.config
        
        assert "call_manager" in config
        assert "websocket" in config
        assert "api" in config
        assert config["call_manager"]["max_concurrent_calls"] == 1000
    
    def test_load_config_from_file(self, tmp_path):
        """Test loading configuration from file."""
        # Create temporary config file
        config_file = tmp_path / "config.json"
        test_config = {
            "call_manager": {
                "max_concurrent_calls": 500
            }
        }
        config_file.write_text(json.dumps(test_config))
        
        # Create server with config file
        server = SIPIntegrationServer(config_path=str(config_file))
        
        assert server.config["call_manager"]["max_concurrent_calls"] == 500


class TestAudioProcessing:
    """Test suite for audio processing components."""
    
    def test_audio_codec_imports(self):
        """Test that audio codec modules can be imported."""
        from src.audio.codecs import AudioProcessor, PCMUCodec, PCMACodec
        
        # Test AudioProcessor
        processor = AudioProcessor()
        assert processor is not None
        
        # Test codec availability
        pcmu_codec = processor.get_codec("PCMU")
        assert pcmu_codec is not None
        
        pcma_codec = processor.get_codec("PCMA")
        assert pcma_codec is not None
    
    def test_rtp_imports(self):
        """Test that RTP modules can be imported."""
        from src.audio.rtp import RTPManager, RTPSession, RTPHeader
        
        # Test RTPManager
        manager = RTPManager()
        assert manager is not None
        
        # Test port allocation
        port = manager.allocate_port()
        assert isinstance(port, int)
        assert 10000 <= port <= 20000
        
        # Test port release
        manager.release_port(port)
        assert port not in manager.used_ports


class TestDatabaseModels:
    """Test suite for database models."""
    
    def test_database_imports(self):
        """Test that database models can be imported."""
        from src.models.database import CallRecord, SMSRecord, RegisteredNumber
        
        # Test model instantiation
        call_record = CallRecord(
            call_id="test-123",
            from_number="+1234567890",
            to_number="+0987654321",
            direction="inbound",
            status="connected",
            start_time=datetime.utcnow()
        )
        assert call_record.call_id == "test-123"
        
        sms_record = SMSRecord(
            message_id="sms-123",
            from_number="+1234567890",
            to_number="+0987654321",
            direction="inbound",
            message="Test message",
            status="delivered"
        )
        assert sms_record.message_id == "sms-123"
    
    @pytest.mark.asyncio
    async def test_database_initialization(self):
        """Test database initialization."""
        from src.models.database import init_db
        
        # Should not raise exception
        await init_db()


# Integration test to verify all components work together
class TestFullIntegration:
    """Integration tests for complete system."""
    
    @pytest.mark.asyncio
    async def test_complete_call_flow(self):
        """Test complete call flow integration."""
        # Create components
        call_manager = CallManager(max_concurrent_calls=10)
        websocket_bridge = WebSocketCallBridge(call_manager)
        
        # Initialize API
        initialize_services(call_manager, websocket_bridge)
        
        # Test incoming call
        sip_data = {
            "call_id": "integration-test-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "sip_call_id": "integration-test-123",
            "remote_ip": "192.168.1.100"
        }
        
        # Handle call through bridge
        result = await websocket_bridge.notify_incoming_call(sip_data)
        assert result["action"] == "accept"
        
        # Verify call is tracked in manager
        call_session = call_manager.get_call_session(result["call_id"])
        assert call_session is not None
        assert call_session.caller.number == "+1234567890"
        
        # Test state updates
        success = await call_manager.update_call_state(
            result["call_id"], 
            CallState.CONNECTED
        )
        assert success == True
        
        # Test hangup
        success = await call_manager.hangup_call(result["call_id"])
        assert success == True
        
        # Verify final state
        call_session = call_manager.get_call_session(result["call_id"])
        assert call_session.state == CallState.COMPLETED
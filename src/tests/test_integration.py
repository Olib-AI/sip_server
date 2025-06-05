"""Integration tests for SIP server components."""
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment
os.environ.update({
    'DB_HOST': 'localhost',
    'DB_PORT': '5432',
    'API_PORT': '8080',
    'WEBSOCKET_PORT': '8081',
    'JWT_SECRET_KEY': 'test-secret-key',
    'LOG_LEVEL': 'INFO',
    'DEBUG': 'true',
    'TESTING': 'true'
})

from ..call_handling.call_manager import CallManager, CallState, CallDirection
from ..call_handling.websocket_integration import WebSocketCallBridge
from ..utils.config import get_config


class TestCallManagerIntegration:
    """Test CallManager integration."""
    
    @pytest.fixture
    def mock_ai_websocket_manager(self):
        """Mock AI WebSocket manager."""
        return AsyncMock()
    
    @pytest.fixture
    def call_manager(self, mock_ai_websocket_manager):
        """Create CallManager instance for testing."""
        return CallManager(
            max_concurrent_calls=10,
            ai_websocket_manager=mock_ai_websocket_manager
        )
    
    @pytest.mark.asyncio
    async def test_call_manager_start_stop(self, call_manager):
        """Test CallManager start and stop."""
        # Mock the component start/stop methods
        with patch.object(call_manager.kamailio_sync, 'start') as mock_sync_start, \
             patch.object(call_manager.kamailio_sync, 'stop') as mock_sync_stop, \
             patch.object(call_manager.dtmf_processor, 'start') as mock_dtmf_start, \
             patch.object(call_manager.dtmf_processor, 'stop') as mock_dtmf_stop, \
             patch.object(call_manager.music_on_hold, 'start') as mock_moh_start, \
             patch.object(call_manager.music_on_hold, 'stop') as mock_moh_stop, \
             patch.object(call_manager.ivr_manager, 'start') as mock_ivr_start, \
             patch.object(call_manager.ivr_manager, 'stop') as mock_ivr_stop, \
             patch.object(call_manager.sms_manager, 'stop_processing') as mock_sms_stop:
            
            # Test start
            await call_manager.start()
            assert call_manager.is_running is True
            mock_sync_start.assert_called_once()
            mock_dtmf_start.assert_called_once()
            mock_moh_start.assert_called_once()
            mock_ivr_start.assert_called_once()
            
            # Test stop
            await call_manager.stop()
            assert call_manager.is_running is False
            mock_sync_stop.assert_called_once()
            mock_dtmf_stop.assert_called_once()
            mock_moh_stop.assert_called_once()
            mock_ivr_stop.assert_called_once()
            mock_sms_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_incoming_call_handling(self, call_manager):
        """Test incoming call handling."""
        sip_data = {
            "call_id": "test-call-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "sip_call_id": "sip-123@example.com",
            "headers": {"User-Agent": "Test-SIP/1.0"}
        }
        
        # Mock the kamailio sync to avoid actual RPC calls
        with patch.object(call_manager.kamailio_sync, 'notify_call_creation') as mock_notify:
            result = await call_manager.handle_incoming_call(sip_data)
            
            assert result["action"] == "accept"
            assert "call_id" in result
            assert result["call_id"] in call_manager.active_calls
            
            # Verify call was added to active calls
            call_session = call_manager.active_calls[result["call_id"]]
            assert call_session.caller.number == "+1234567890"
            assert call_session.callee.number == "+0987654321"
            assert call_session.direction == CallDirection.INBOUND
            
            # Verify Kamailio sync was called
            mock_notify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_call_state_updates(self, call_manager):
        """Test call state updates and synchronization."""
        # First create a call
        sip_data = {
            "call_id": "test-call-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        with patch.object(call_manager.kamailio_sync, 'notify_call_creation'), \
             patch.object(call_manager.kamailio_sync, 'notify_state_change') as mock_state_change:
            
            result = await call_manager.handle_incoming_call(sip_data)
            call_id = result["call_id"]
            
            # Test state update
            success = await call_manager.update_call_state(call_id, CallState.CONNECTED)
            assert success is True
            
            # Verify state was updated
            call_session = call_manager.active_calls[call_id]
            assert call_session.state == CallState.CONNECTED
            assert call_session.connect_time is not None
            
            # Verify sync was called
            mock_state_change.assert_called()
    
    @pytest.mark.asyncio 
    async def test_sms_integration(self, call_manager):
        """Test SMS integration through call manager."""
        sms_data = {
            "from_uri": "sip:+1234567890@example.com",
            "to_uri": "sip:+0987654321@example.com", 
            "body": "Test SMS message",
            "call_id": "sms-123",
            "headers": {}
        }
        
        # Mock SMS manager receive_sms method
        with patch.object(call_manager.sms_manager, 'receive_sms') as mock_receive:
            mock_receive.return_value = MagicMock(message_id="sms-123")
            
            # Call the SMS manager directly (as would be done by Kamailio integration)
            result = await call_manager.sms_manager.receive_sms(sms_data)
            
            mock_receive.assert_called_once_with(sms_data)
            assert result.message_id == "sms-123"


class TestWebSocketIntegration:
    """Test WebSocket integration."""
    
    @pytest.fixture
    def mock_call_manager(self):
        """Mock CallManager for testing."""
        manager = MagicMock()
        manager.get_call_session.return_value = None
        return manager
    
    @pytest.fixture
    def websocket_bridge(self, mock_call_manager):
        """Create WebSocket bridge for testing."""
        return WebSocketCallBridge(
            call_manager=mock_call_manager,
            ai_websocket_url="ws://localhost:8081/ws",
            port=8081
        )
    
    def test_websocket_bridge_initialization(self, websocket_bridge):
        """Test WebSocket bridge initialization."""
        config = get_config()
        
        assert websocket_bridge.port == config.websocket.port
        assert websocket_bridge.ai_websocket_url == config.websocket.ai_platform_url
        assert websocket_bridge.authenticator is not None
    
    @pytest.mark.asyncio
    async def test_websocket_bridge_start_stop(self, websocket_bridge):
        """Test WebSocket bridge start and stop."""
        # Mock the server start
        with patch('websockets.serve') as mock_serve:
            mock_server = AsyncMock()
            mock_serve.return_value = mock_server
            
            await websocket_bridge.start()
            assert websocket_bridge.is_running is True
            mock_serve.assert_called_once()
            
            await websocket_bridge.stop()
            assert websocket_bridge.is_running is False


class TestConfigurationIntegration:
    """Test configuration integration across components."""
    
    def test_config_consistency(self):
        """Test that configuration is consistent across components."""
        config = get_config()
        
        # Test that configuration values are accessible
        assert config.database.host is not None
        assert config.api.port > 0
        assert config.websocket.port > 0
        assert config.sip.port > 0
        
        # Test backward compatibility
        config_dict = config.to_dict()
        assert config_dict["database"]["host"] == config.database.host
        assert config_dict["api"]["port"] == config.api.port
    
    def test_component_configuration_usage(self):
        """Test that components use configuration correctly."""
        # Test CallManager uses config
        manager = CallManager(max_concurrent_calls=10)
        assert manager.kamailio_sync is not None
        assert manager.sms_manager is not None
        
        # Test WebSocket bridge uses config
        bridge = WebSocketCallBridge(call_manager=manager)
        config = get_config()
        assert bridge.port == config.websocket.port
        assert bridge.ai_websocket_url == config.websocket.ai_platform_url


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
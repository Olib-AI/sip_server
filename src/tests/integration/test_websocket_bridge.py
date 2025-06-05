"""Integration tests for WebSocket bridge functionality."""
import pytest
import asyncio
import json
import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch
import websockets
from websockets.exceptions import ConnectionClosed

from src.websocket.bridge import WebSocketBridge, CallState, MessageType, CallInfo
from src.websocket.bridge_handlers import BridgeHandlers
from src.audio.codecs import AudioProcessor


class TestWebSocketBridge:
    """Test suite for WebSocket bridge functionality."""
    
    @pytest.fixture
    async def websocket_bridge(self):
        """Create WebSocket bridge instance."""
        ai_platform_url = "ws://localhost:8001/ws/voice"
        bridge = WebSocketBridge(ai_platform_url, sip_ws_port=8080)
        
        # Mock the AI platform connection
        with patch('websockets.connect') as mock_connect:
            mock_websocket = AsyncMock()
            mock_connect.return_value = mock_websocket
            await bridge.start()
            
        yield bridge
        await bridge.stop()
    
    @pytest.fixture
    def sample_call_info(self):
        """Sample call information."""
        return CallInfo(
            call_id="test-call-123",
            from_number="+1234567890",
            to_number="+0987654321",
            sip_headers={"User-Agent": "Test/1.0"},
            state=CallState.CONNECTING,
            codec="PCMU",
            ai_session_id="ai-session-456"
        )
    
    @pytest.fixture
    def sample_audio_data(self):
        """Sample audio data for testing."""
        # Generate 20ms of PCMU audio (160 bytes)
        return b'\x00' * 160

    @pytest.mark.asyncio
    async def test_websocket_bridge_initialization(self, websocket_bridge):
        """Test WebSocket bridge initialization."""
        assert websocket_bridge.ai_platform_url == "ws://localhost:8001/ws/voice"
        assert websocket_bridge.sip_ws_port == 8080
        assert websocket_bridge.running is True
        assert websocket_bridge.audio_processor is not None
        assert websocket_bridge.rtp_manager is not None
        assert websocket_bridge.connection_manager is not None

    @pytest.mark.asyncio
    async def test_sip_connection_handling(self, websocket_bridge, sample_call_info):
        """Test SIP WebSocket connection handling."""
        # Mock SIP WebSocket connection
        mock_sip_websocket = AsyncMock()
        
        # Mock the connection setup message
        call_setup_message = {
            "type": "call_setup",
            "call_id": "test-call-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "codec": "PCMU",
            "sip_headers": {"User-Agent": "Test/1.0"}
        }
        
        # Simulate receiving setup message
        mock_sip_websocket.recv.return_value = json.dumps(call_setup_message)
        
        # Mock RTP session setup
        with patch.object(websocket_bridge.rtp_manager, 'create_session') as mock_create_session:
            mock_rtp_session = MagicMock()
            mock_rtp_session.local_port = 12345
            mock_create_session.return_value = mock_rtp_session
            
            # Mock AI platform connection
            with patch.object(websocket_bridge.connection_manager, 'connect_for_call') as mock_ai_connect:
                mock_ai_connection = AsyncMock()
                mock_ai_connect.return_value = mock_ai_connection
                
                # Test SIP connection handling
                await websocket_bridge.handle_sip_connection(mock_sip_websocket, "/")
                
                # Verify call was registered
                assert "test-call-123" in websocket_bridge.active_calls
                call_info = websocket_bridge.active_calls["test-call-123"]
                assert call_info.call_id == "test-call-123"
                assert call_info.from_number == "+1234567890"

    @pytest.mark.asyncio
    async def test_ai_platform_connection(self, websocket_bridge, sample_call_info):
        """Test AI platform connection management."""
        # Test connecting to AI platform
        with patch('websockets.connect') as mock_connect:
            mock_websocket = AsyncMock()
            mock_connect.return_value = mock_websocket
            
            connection = await websocket_bridge.connection_manager.connect_for_call(
                "test-call-123", sample_call_info
            )
            
            assert connection is not None
            assert "test-call-123" in websocket_bridge.connection_manager.connections
            
            # Verify call start message was sent
            mock_websocket.send.assert_called()
            sent_message = json.loads(mock_websocket.send.call_args[0][0])
            assert sent_message["type"] == "call_start"
            assert sent_message["data"]["call_id"] == "test-call-123"

    @pytest.mark.asyncio
    async def test_audio_streaming_to_ai(self, websocket_bridge, sample_call_info, sample_audio_data):
        """Test audio streaming to AI platform."""
        # Setup call
        websocket_bridge.active_calls["test-call-123"] = sample_call_info
        
        # Mock AI connection
        mock_ai_connection = AsyncMock()
        websocket_bridge.connection_manager.connections["test-call-123"] = mock_ai_connection
        
        # Test audio streaming
        success = await websocket_bridge.connection_manager.send_audio("test-call-123", sample_audio_data)
        
        assert success is True
        mock_ai_connection.send.assert_called()
        
        # Verify audio message format
        sent_message = json.loads(mock_ai_connection.send.call_args[0][0])
        assert sent_message["type"] == "audio_data"
        assert sent_message["data"]["call_id"] == "test-call-123"
        assert "audio" in sent_message["data"]
        
        # Verify audio is base64 encoded
        decoded_audio = base64.b64decode(sent_message["data"]["audio"])
        assert decoded_audio == sample_audio_data

    @pytest.mark.asyncio
    async def test_audio_processing_from_rtp(self, websocket_bridge, sample_call_info, sample_audio_data):
        """Test audio processing from RTP."""
        # Setup call and audio buffer
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        websocket_bridge.audio_buffers[call_id] = websocket_bridge.AudioBuffer()
        
        # Mock AI connection
        mock_ai_connection = AsyncMock()
        websocket_bridge.connection_manager.connections[call_id] = mock_ai_connection
        
        # Mock audio processor
        with patch.object(websocket_bridge.audio_processor, 'convert_format') as mock_convert:
            with patch.object(websocket_bridge.audio_processor, 'apply_agc') as mock_agc:
                mock_convert.return_value = sample_audio_data
                mock_agc.return_value = sample_audio_data
                
                # Process RTP audio
                await websocket_bridge._handle_rtp_audio(call_id, sample_audio_data)
                
                # Verify audio processing chain
                mock_convert.assert_called_with(sample_audio_data, "PCMU", "PCM")
                mock_agc.assert_called_with(sample_audio_data)

    @pytest.mark.asyncio
    async def test_audio_from_ai_to_rtp(self, websocket_bridge, sample_call_info, sample_audio_data):
        """Test audio processing from AI to RTP."""
        # Setup call
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        
        # Mock RTP session
        mock_rtp_session = AsyncMock()
        websocket_bridge.rtp_manager.sessions = {call_id: mock_rtp_session}
        
        # Mock SIP WebSocket
        mock_sip_ws = AsyncMock()
        websocket_bridge.sip_connections[call_id] = mock_sip_ws
        
        # Mock audio processor
        with patch.object(websocket_bridge.audio_processor, 'convert_format') as mock_convert:
            mock_convert.return_value = sample_audio_data
            
            # Process AI audio
            await websocket_bridge._handle_ai_audio(call_id, sample_audio_data)
            
            # Verify audio was sent via RTP and WebSocket
            mock_convert.assert_called_with(sample_audio_data, "PCM", "PCMU")
            mock_rtp_session.send_audio.assert_called()
            mock_sip_ws.send.assert_called()

    @pytest.mark.asyncio
    async def test_dtmf_forwarding(self, websocket_bridge, sample_call_info):
        """Test DTMF forwarding to AI platform."""
        # Setup call
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        
        # Mock AI connection
        mock_ai_connection = AsyncMock()
        websocket_bridge.connection_manager.connections[call_id] = mock_ai_connection
        
        # Test DTMF forwarding
        await websocket_bridge._forward_dtmf_to_ai(call_id, "1")
        
        # Verify DTMF message was sent
        mock_ai_connection.send.assert_called()
        sent_message = json.loads(mock_ai_connection.send.call_args[0][0])
        assert sent_message["type"] == "dtmf"
        assert sent_message["data"]["digit"] == "1"
        assert sent_message["data"]["call_id"] == call_id

    @pytest.mark.asyncio
    async def test_call_control_messages(self, websocket_bridge, sample_call_info):
        """Test call control messages from AI."""
        # Setup call
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        
        # Mock SIP WebSocket
        mock_sip_ws = AsyncMock()
        websocket_bridge.sip_connections[call_id] = mock_sip_ws
        
        # Test hangup command
        await websocket_bridge._process_ai_control_message(call_id, {"type": "hangup"})
        
        # Verify hangup message was sent to SIP
        mock_sip_ws.send.assert_called()
        sent_message = json.loads(mock_sip_ws.send.call_args[0][0])
        assert sent_message["type"] == "hangup"

    @pytest.mark.asyncio
    async def test_call_transfer_from_ai(self, websocket_bridge, sample_call_info):
        """Test call transfer initiated by AI."""
        # Setup call
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        
        # Mock SIP WebSocket
        mock_sip_ws = AsyncMock()
        websocket_bridge.sip_connections[call_id] = mock_sip_ws
        
        # Test transfer command
        transfer_data = {"type": "transfer", "target": "+5555555555"}
        await websocket_bridge._process_ai_control_message(call_id, transfer_data)
        
        # Verify transfer message was sent to SIP
        mock_sip_ws.send.assert_called()
        sent_message = json.loads(mock_sip_ws.send.call_args[0][0])
        assert sent_message["type"] == "transfer"
        assert sent_message["target"] == "+5555555555"

    @pytest.mark.asyncio
    async def test_call_hold_resume(self, websocket_bridge, sample_call_info):
        """Test call hold and resume functionality."""
        # Setup call
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        
        # Test hold
        await websocket_bridge._handle_call_hold(call_id)
        assert websocket_bridge.active_calls[call_id].state == CallState.ON_HOLD
        
        # Test resume
        await websocket_bridge._handle_call_resume(call_id)
        assert websocket_bridge.active_calls[call_id].state == CallState.CONNECTED

    @pytest.mark.asyncio
    async def test_connection_recovery(self, websocket_bridge, sample_call_info):
        """Test connection recovery and retry logic."""
        # Mock failed connection
        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = ConnectionRefusedError("Connection failed")
            
            # Attempt connection with retry
            connection = await websocket_bridge.connection_manager.connect_for_call(
                "test-call-123", sample_call_info
            )
            
            # Should return None after max retries
            assert connection is None

    @pytest.mark.asyncio
    async def test_audio_buffer_management(self, websocket_bridge):
        """Test audio buffer and jitter control."""
        from src.websocket.bridge import AudioBuffer
        
        buffer = AudioBuffer(max_frames=5, target_delay_ms=60)
        
        # Add audio frames
        for i in range(3):
            buffer.add_frame(b'\x00' * 160)
        
        assert buffer.get_buffer_level() == 0.6  # 3/5 frames
        
        # Wait for target delay (simulate)
        import time
        time.sleep(0.1)
        
        # Get frame after delay
        frame = buffer.get_frame()
        assert frame is not None
        assert len(frame) == 160

    @pytest.mark.asyncio
    async def test_call_cleanup(self, websocket_bridge, sample_call_info):
        """Test call cleanup and resource management."""
        # Setup call
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        websocket_bridge.audio_buffers[call_id] = websocket_bridge.AudioBuffer()
        
        # Mock connections
        mock_ai_connection = AsyncMock()
        mock_sip_connection = AsyncMock()
        websocket_bridge.connection_manager.connections[call_id] = mock_ai_connection
        websocket_bridge.sip_connections[call_id] = mock_sip_connection
        
        # Mock RTP session
        mock_rtp_session = AsyncMock()
        websocket_bridge.rtp_manager.sessions = {call_id: mock_rtp_session}
        
        # Cleanup call
        await websocket_bridge.cleanup_call(call_id, "test cleanup")
        
        # Verify cleanup
        assert call_id not in websocket_bridge.active_calls
        assert call_id not in websocket_bridge.audio_buffers
        assert call_id not in websocket_bridge.sip_connections
        
        # Verify connections were closed
        mock_ai_connection.send.assert_called()  # Call end message
        mock_sip_connection.close.assert_called()

    @pytest.mark.asyncio
    async def test_statistics_collection(self, websocket_bridge):
        """Test statistics collection."""
        # Get initial statistics
        stats = websocket_bridge.get_statistics()
        
        assert "uptime_seconds" in stats
        assert "total_calls_handled" in stats
        assert "concurrent_calls" in stats
        assert "active_calls" in stats
        assert stats["total_calls_handled"] >= 0

    @pytest.mark.asyncio
    async def test_heartbeat_functionality(self, websocket_bridge, sample_call_info):
        """Test heartbeat and connection monitoring."""
        # Setup call with AI connection
        call_id = "test-call-123"
        websocket_bridge.active_calls[call_id] = sample_call_info
        
        # Mock AI connection
        mock_ai_connection = AsyncMock()
        mock_ai_connection.ping = AsyncMock()
        websocket_bridge.connection_manager.connections[call_id] = mock_ai_connection
        
        # Simulate heartbeat loop iteration
        await websocket_bridge._heartbeat_loop()
        
        # Verify ping was called
        mock_ai_connection.ping.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_in_bridge(self, websocket_bridge):
        """Test error handling in WebSocket bridge."""
        # Test with invalid call ID
        result = await websocket_bridge._handle_rtp_audio("invalid-call", b'\x00' * 160)
        # Should not raise exception, just log and continue
        
        # Test with malformed SIP message
        mock_websocket = AsyncMock()
        mock_websocket.recv.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        # Should handle JSON decode error gracefully
        try:
            await websocket_bridge._handle_sip_messages(mock_websocket, "test-call")
        except json.JSONDecodeError:
            pytest.fail("JSON decode error should be handled gracefully")

    @pytest.mark.asyncio
    async def test_concurrent_call_handling(self, websocket_bridge):
        """Test handling multiple concurrent calls."""
        # Create multiple calls
        call_ids = []
        for i in range(3):
            call_id = f"concurrent-call-{i}"
            call_info = CallInfo(
                call_id=call_id,
                from_number=f"+123456789{i}",
                to_number="+0987654321",
                sip_headers={},
                codec="PCMU"
            )
            websocket_bridge.active_calls[call_id] = call_info
            call_ids.append(call_id)
        
        # Verify all calls are tracked
        assert len(websocket_bridge.active_calls) == 3
        
        # Cleanup all calls
        for call_id in call_ids:
            await websocket_bridge.cleanup_call(call_id, "test")
        
        assert len(websocket_bridge.active_calls) == 0

    @pytest.mark.asyncio
    async def test_websocket_message_protocols(self, websocket_bridge):
        """Test WebSocket message protocol compliance."""
        # Test message type enumeration
        assert MessageType.CALL_START.value == "call_start"
        assert MessageType.AUDIO_DATA.value == "audio_data"
        assert MessageType.DTMF.value == "dtmf"
        assert MessageType.CALL_END.value == "call_end"
        
        # Test call state enumeration
        assert CallState.INITIALIZING.value == "initializing"
        assert CallState.CONNECTED.value == "connected"
        assert CallState.ON_HOLD.value == "on_hold"
        assert CallState.ENDING.value == "ending"
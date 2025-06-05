"""WebSocket bridge tests."""
import pytest
import asyncio
import json
import websockets
from unittest.mock import AsyncMock, MagicMock, patch

from ..websocket.bridge import WebSocketBridge, CallInfo, CallState, MessageType, AudioProcessor


class TestAudioProcessor:
    """Test audio format conversion."""
    
    def test_ulaw_to_pcm_conversion(self):
        """Test μ-law to PCM conversion."""
        processor = AudioProcessor()
        # Test with sample μ-law data
        ulaw_data = b'\xff\x00\x7f\x80'  # Sample μ-law bytes
        pcm_data = processor.ulaw_to_pcm(ulaw_data)
        assert isinstance(pcm_data, bytes)
        assert len(pcm_data) == len(ulaw_data) * 2  # PCM is 16-bit
        
    def test_pcm_to_ulaw_conversion(self):
        """Test PCM to μ-law conversion."""
        processor = AudioProcessor()
        # Test with sample PCM data
        pcm_data = b'\x00\x00\xff\xff\x00\x80\xff\x7f'  # Sample 16-bit PCM
        ulaw_data = processor.pcm_to_ulaw(pcm_data)
        assert isinstance(ulaw_data, bytes)
        assert len(ulaw_data) == len(pcm_data) // 2  # μ-law is 8-bit
        
    def test_resample_same_rate(self):
        """Test resampling with same rate."""
        processor = AudioProcessor()
        data = b'\x00\x00\xff\xff'
        resampled = processor.resample(data, 8000, 8000)
        assert resampled == data
        
    def test_alaw_conversions(self):
        """Test A-law conversions."""
        processor = AudioProcessor()
        alaw_data = b'\xd5\x55\x2a\xaa'
        
        # A-law to PCM
        pcm_data = processor.alaw_to_pcm(alaw_data)
        assert isinstance(pcm_data, bytes)
        assert len(pcm_data) == len(alaw_data) * 2
        
        # PCM to A-law
        alaw_converted = processor.pcm_to_alaw(pcm_data)
        assert isinstance(alaw_converted, bytes)
        assert len(alaw_converted) == len(pcm_data) // 2


@pytest.mark.asyncio
class TestWebSocketBridge:
    """Test WebSocket bridge functionality."""
    
    async def test_bridge_initialization(self):
        """Test bridge initialization."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice", 8080)
        assert bridge.ai_platform_url == "ws://localhost:8001/ws/voice"
        assert bridge.sip_ws_port == 8080
        assert isinstance(bridge.audio_processor, AudioProcessor)
        assert len(bridge.active_calls) == 0
        
    @patch('websockets.serve')
    async def test_bridge_start(self, mock_serve):
        """Test bridge start."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        mock_serve.return_value = AsyncMock()
        
        # Create a task that will be cancelled
        task = asyncio.create_task(bridge.start())
        await asyncio.sleep(0.1)
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
            
        mock_serve.assert_called_once()
        
    async def test_handle_sip_connection_invalid_start(self):
        """Test handling invalid SIP connection start."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        
        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "invalid_type"
        })
        
        await bridge.handle_sip_connection(mock_ws, "/")
        
        # Should send error
        mock_ws.send.assert_called_once()
        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["type"] == MessageType.ERROR.value
        
    @patch('websockets.connect')
    async def test_connect_to_ai_platform(self, mock_connect):
        """Test connecting to AI platform."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        
        # Setup call info
        call_id = "test-call-123"
        bridge.active_calls[call_id] = CallInfo(
            call_id=call_id,
            from_number="+1234567890",
            to_number="+0987654321",
            sip_headers={"X-Custom": "value"}
        )
        
        # Mock AI WebSocket
        mock_ai_ws = AsyncMock()
        mock_connect.return_value = mock_ai_ws
        
        await bridge.connect_to_ai_platform(call_id)
        
        # Verify connection
        mock_connect.assert_called_once_with(
            bridge.ai_platform_url,
            extra_headers={
                "X-Call-ID": call_id,
                "X-Source": "sip"
            }
        )
        
        # Verify initial data sent
        mock_ai_ws.send.assert_called_once()
        sent_data = json.loads(mock_ai_ws.send.call_args[0][0])
        assert sent_data["call_id"] == call_id
        assert sent_data["source"] == "sip"
        
    async def test_process_sip_control_messages(self):
        """Test processing SIP control messages."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        call_id = "test-call-123"
        
        # Mock AI connection
        mock_ai_ws = AsyncMock()
        bridge.ai_connections[call_id] = mock_ai_ws
        
        # Test DTMF message
        dtmf_data = {
            "type": MessageType.DTMF.value,
            "digit": "5"
        }
        await bridge.process_sip_control_message(call_id, dtmf_data)
        mock_ai_ws.send.assert_called_once()
        
        # Test call end message
        bridge.active_calls[call_id] = CallInfo(
            call_id=call_id,
            from_number="+1234567890",
            to_number="+0987654321",
            sip_headers={}
        )
        
        end_data = {"type": MessageType.CALL_END.value}
        with patch.object(bridge, 'end_call') as mock_end_call:
            await bridge.process_sip_control_message(call_id, end_data)
            mock_end_call.assert_called_once_with(call_id)
            
    async def test_process_ai_control_messages(self):
        """Test processing AI control messages."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        call_id = "test-call-123"
        
        # Mock SIP connection
        mock_sip_ws = AsyncMock()
        bridge.sip_connections[call_id] = mock_sip_ws
        
        # Test hangup message
        bridge.active_calls[call_id] = CallInfo(
            call_id=call_id,
            from_number="+1234567890",
            to_number="+0987654321",
            sip_headers={}
        )
        
        hangup_data = {"type": "hangup"}
        with patch.object(bridge, 'end_call') as mock_end_call:
            await bridge.process_ai_control_message(call_id, hangup_data)
            mock_end_call.assert_called_once_with(call_id)
            
        # Test transfer message
        transfer_data = {
            "type": "transfer",
            "target": "+1122334455"
        }
        await bridge.process_ai_control_message(call_id, transfer_data)
        mock_sip_ws.send.assert_called()
        sent_data = json.loads(mock_sip_ws.send.call_args[0][0])
        assert sent_data["type"] == MessageType.CALL_TRANSFER.value
        assert sent_data["target"] == "+1122334455"
        
    async def test_audio_streaming(self):
        """Test audio streaming from SIP to AI."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        call_id = "test-call-123"
        
        # Setup
        bridge.active_calls[call_id] = CallInfo(
            call_id=call_id,
            from_number="+1234567890",
            to_number="+0987654321",
            sip_headers={}
        )
        
        mock_ai_ws = AsyncMock()
        bridge.ai_connections[call_id] = mock_ai_ws
        
        audio_queue = asyncio.Queue()
        bridge.audio_buffers[call_id] = audio_queue
        
        # Add test audio data
        test_audio = b'\xff\x00\x7f\x80'  # μ-law audio
        await audio_queue.put(test_audio)
        
        # Run streaming (with timeout)
        stream_task = asyncio.create_task(bridge.stream_audio_to_ai(call_id))
        await asyncio.sleep(0.2)
        
        # Clean up
        del bridge.active_calls[call_id]
        await asyncio.sleep(0.1)
        stream_task.cancel()
        
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
            
        # Verify audio was sent
        mock_ai_ws.send.assert_called()
        
    async def test_cleanup_call(self):
        """Test call cleanup."""
        bridge = WebSocketBridge("ws://localhost:8001/ws/voice")
        call_id = "test-call-123"
        
        # Setup connections and data
        mock_ai_ws = AsyncMock()
        mock_sip_ws = AsyncMock()
        
        bridge.active_calls[call_id] = CallInfo(
            call_id=call_id,
            from_number="+1234567890",
            to_number="+0987654321",
            sip_headers={}
        )
        bridge.ai_connections[call_id] = mock_ai_ws
        bridge.sip_connections[call_id] = mock_sip_ws
        bridge.audio_buffers[call_id] = asyncio.Queue()
        
        # Cleanup
        await bridge.cleanup_call(call_id)
        
        # Verify cleanup
        assert call_id not in bridge.active_calls
        assert call_id not in bridge.ai_connections
        assert call_id not in bridge.sip_connections
        assert call_id not in bridge.audio_buffers
        
        mock_ai_ws.close.assert_called_once()
        mock_sip_ws.close.assert_called_once()
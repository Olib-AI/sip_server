"""SIP client tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import json

from src.utils.sip_client import SIPClient
from src.models.schemas import CallInfo, SMSInfo, CallStatus, SMSStatus


@pytest.mark.asyncio
class TestSIPClient:
    """Test SIP client functionality."""
    
    async def test_client_initialization(self):
        """Test SIP client initialization."""
        client = SIPClient("http://localhost:5060")
        assert client.kamailio_url == "http://localhost:5060"
        assert client.rpc_url == "http://localhost:5060/RPC"
        assert client.client is not None
        
    async def test_client_close(self):
        """Test client cleanup."""
        client = SIPClient()
        await client.close()
        
    @patch('httpx.AsyncClient.post')
    async def test_rpc_call_success(self, mock_post):
        """Test successful RPC call."""
        client = SIPClient()
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "success"},
            "id": 1
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = await client._rpc_call("test.method", ["param1", "param2"])
        
        assert result == {"status": "success"}
        mock_post.assert_called_once()
        
    @patch('httpx.AsyncClient.post')
    async def test_rpc_call_error(self, mock_post):
        """Test RPC call with error."""
        client = SIPClient()
        
        # Mock error response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "error": {"code": -1, "message": "Test error"},
            "id": 1
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        with pytest.raises(Exception) as exc_info:
            await client._rpc_call("test.method")
            
        assert "RPC error" in str(exc_info.value)
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_initiate_call(self, mock_rpc):
        """Test call initiation."""
        client = SIPClient()
        mock_rpc.return_value = {"status": "success"}
        
        call_info = await client.initiate_call(
            from_number="+1234567890",
            to_number="+0987654321",
            headers={"X-Custom": "value"},
            webhook_url="https://example.com/webhook"
        )
        
        assert isinstance(call_info, CallInfo)
        assert call_info.from_number == "+1234567890"
        assert call_info.to_number == "+0987654321"
        assert call_info.status == CallStatus.CONNECTING
        assert call_info.direction == "outbound"
        
        mock_rpc.assert_called_once()
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_get_active_calls(self, mock_rpc):
        """Test getting active calls."""
        client = SIPClient()
        
        # Mock dialog list
        mock_rpc.return_value = [
            {
                "callid": "call-123",
                "from_uri": "sip:+1234567890@sip.olib.ai",
                "to_uri": "sip:+0987654321@sip.olib.ai",
                "state": 3,
                "direction": "outbound",
                "start_ts": 1640995200
            }
        ]
        
        calls = await client.get_active_calls()
        
        assert len(calls) == 1
        assert isinstance(calls[0], CallInfo)
        assert calls[0].call_id == "call-123"
        assert calls[0].from_number == "+1234567890"
        assert calls[0].to_number == "+0987654321"
        assert calls[0].status == CallStatus.CONNECTED
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_get_call_info(self, mock_rpc):
        """Test getting specific call info."""
        client = SIPClient()
        
        mock_rpc.return_value = {
            "callid": "call-123",
            "from_uri": "sip:+1234567890@sip.olib.ai",
            "to_uri": "sip:+0987654321@sip.olib.ai", 
            "state": 3,
            "direction": "inbound",
            "start_ts": 1640995200,
            "end_ts": 1640995260
        }
        
        call_info = await client.get_call_info("call-123")
        
        assert call_info is not None
        assert call_info.call_id == "call-123"
        assert call_info.duration == 60
        assert call_info.end_time is not None
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_hangup_call(self, mock_rpc):
        """Test hanging up a call."""
        client = SIPClient()
        mock_rpc.return_value = None
        
        result = await client.hangup_call("call-123")
        
        assert result is True
        mock_rpc.assert_called_once_with("dlg.terminate_dlg", ["call-123"])
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_transfer_call(self, mock_rpc):
        """Test call transfer."""
        client = SIPClient()
        mock_rpc.return_value = None
        
        result = await client.transfer_call(
            "call-123",
            "+1122334455",
            blind_transfer=True
        )
        
        assert result is True
        mock_rpc.assert_called_once()
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_send_sms(self, mock_rpc):
        """Test SMS sending."""
        client = SIPClient()
        mock_rpc.return_value = None
        
        sms_info = await client.send_sms(
            from_number="+1234567890",
            to_number="+0987654321",
            message="Test message",
            webhook_url="https://example.com/webhook"
        )
        
        assert isinstance(sms_info, SMSInfo)
        assert sms_info.from_number == "+1234567890"
        assert sms_info.to_number == "+0987654321"
        assert sms_info.message == "Test message"
        assert sms_info.status == SMSStatus.SENT
        assert sms_info.direction == "outbound"
        assert sms_info.segments == 1
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_block_number(self, mock_rpc):
        """Test number blocking."""
        client = SIPClient()
        mock_rpc.return_value = None
        
        result = await client.block_number(
            "+1234567890",
            reason="Test block"
        )
        
        assert result is True
        mock_rpc.assert_called_once()
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_is_number_blocked(self, mock_rpc):
        """Test checking if number is blocked."""
        client = SIPClient()
        
        # Test blocked number
        mock_rpc.return_value = {"blocked": True}
        result = await client.is_number_blocked("+1234567890")
        assert result is True
        
        # Test non-blocked number
        mock_rpc.return_value = None
        result = await client.is_number_blocked("+0987654321")
        assert result is False
        
    def test_extract_number(self):
        """Test extracting number from SIP URI."""
        client = SIPClient()
        
        # Test SIP URI
        assert client._extract_number("sip:+1234567890@sip.olib.ai") == "+1234567890"
        
        # Test with display name
        assert client._extract_number("\"John Doe\" <sip:+1234567890@sip.olib.ai>") == "\"John Doe\" <"
        
        # Test plain number
        assert client._extract_number("+1234567890") == "+1234567890"
        
        # Test empty
        assert client._extract_number("") == ""
        
    def test_map_dialog_state(self):
        """Test mapping dialog state to CallStatus."""
        client = SIPClient()
        
        assert client._map_dialog_state(1) == CallStatus.CONNECTING
        assert client._map_dialog_state(3) == CallStatus.CONNECTED
        assert client._map_dialog_state(5) == CallStatus.ENDED
        assert client._map_dialog_state(99) == CallStatus.FAILED
        
    def test_calculate_segments(self):
        """Test SMS segment calculation."""
        client = SIPClient()
        
        # Single segment
        assert client._calculate_segments("Short message") == 1
        
        # Multiple segments
        long_message = "x" * 200
        assert client._calculate_segments(long_message) > 1
        
        # Max segments
        very_long_message = "x" * 2000
        assert client._calculate_segments(very_long_message) == 10
        
    @patch.object(SIPClient, '_rpc_call')
    async def test_error_handling(self, mock_rpc):
        """Test error handling in SIP client."""
        client = SIPClient()
        
        # Simulate RPC error
        mock_rpc.side_effect = Exception("RPC error")
        
        # Test that errors are handled gracefully
        calls = await client.get_active_calls()
        assert calls == []
        
        result = await client.hangup_call("call-123")
        assert result is False
        
        blocked_numbers = await client.get_blocked_numbers()
        assert blocked_numbers == []
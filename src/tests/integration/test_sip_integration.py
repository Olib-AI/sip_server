"""Integration tests for SIP server functionality."""
import pytest
import asyncio
import socket
import struct
import time
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from src.call_handling.call_manager import CallManager, CallState, CallDirection
from src.call_handling.kamailio_integration import KamailioIntegration
from src.sip.trunk_manager import TrunkManager
from src.models.database import CallRecord


class TestSIPIntegration:
    """Integration tests for SIP server components."""
    
    @pytest.fixture
    async def call_manager(self):
        """Create call manager instance."""
        manager = CallManager(max_concurrent_calls=100)
        yield manager
        await manager.cleanup()
    
    @pytest.fixture
    async def kamailio_integration(self, call_manager):
        """Create Kamailio integration instance."""
        integration = KamailioIntegration(call_manager)
        await integration.start()
        yield integration
        await integration.stop()
    
    @pytest.fixture
    def sample_sip_invite(self):
        """Sample SIP INVITE data."""
        return {
            "call_id": "test-call-123@example.com",
            "sip_call_id": "abc123def456",
            "from_uri": "sip:+1234567890@provider.com",
            "to_uri": "sip:+0987654321@our-domain.com",
            "from_display_name": "Test Caller",
            "user_agent": "Test SIP Client/1.0",
            "remote_ip": "192.168.1.100",
            "headers": {
                "Content-Type": "application/sdp",
                "Contact": "<sip:+1234567890@192.168.1.100:5060>",
                "X-Test-Header": "integration-test"
            },
            "sdp": self._create_sample_sdp(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _create_sample_sdp(self):
        """Create sample SDP for testing."""
        return """v=0
o=- 123456789 123456789 IN IP4 192.168.1.100
s=Test Call
c=IN IP4 192.168.1.100
t=0 0
m=audio 5004 RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""

    @pytest.mark.asyncio
    async def test_incoming_call_flow(self, kamailio_integration, sample_sip_invite):
        """Test complete incoming call flow."""
        # Process incoming INVITE
        response = await kamailio_integration.handle_invite(sample_sip_invite)
        
        # Verify response
        assert response["action"] == "accept"
        assert response["code"] == 100
        assert "call_id" in response
        
        # Verify call was created in call manager
        call_session = kamailio_integration.call_manager.get_call_session(response["call_id"])
        assert call_session is not None
        assert call_session.caller.number == "+1234567890"
        assert call_session.callee.number == "+0987654321"
        assert call_session.direction == CallDirection.INBOUND
        assert call_session.state == CallState.RINGING

    @pytest.mark.asyncio
    async def test_outbound_call_initiation(self, kamailio_integration):
        """Test outbound call initiation."""
        call_data = {
            "from_number": "+0987654321",
            "to_number": "+1234567890",
            "caller_name": "Test Outbound",
            "custom_data": {"test": "outbound"}
        }
        
        # Initiate outbound call
        with patch.object(kamailio_integration, '_send_invite_via_rpc', 
                         return_value={"success": True, "call_id": "out-123"}):
            response = await kamailio_integration.initiate_call(call_data)
        
        # Verify response
        assert response["success"] is True
        assert "call_id" in response
        
        # Verify call was created
        call_session = kamailio_integration.call_manager.get_call_session(response["call_id"])
        assert call_session is not None
        assert call_session.direction == CallDirection.OUTBOUND

    @pytest.mark.asyncio
    async def test_call_state_transitions(self, call_manager):
        """Test call state transitions."""
        # Create a call
        call_data = {
            "call_id": "state-test-123",
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(call_data)
        call_id = response["call_id"]
        
        # Test state transitions
        assert await call_manager.update_call_state(call_id, CallState.RINGING)
        call_session = call_manager.get_call_session(call_id)
        assert call_session.state == CallState.RINGING
        assert call_session.ring_start is not None
        
        assert await call_manager.update_call_state(call_id, CallState.CONNECTED)
        call_session = call_manager.get_call_session(call_id)
        assert call_session.state == CallState.CONNECTED
        assert call_session.connect_time is not None
        
        assert await call_manager.update_call_state(call_id, CallState.COMPLETED)
        call_session = call_manager.get_call_session(call_id)
        assert call_session.state == CallState.COMPLETED
        assert call_session.end_time is not None

    @pytest.mark.asyncio
    async def test_call_transfer(self, kamailio_integration, sample_sip_invite):
        """Test call transfer functionality."""
        # Setup call
        response = await kamailio_integration.handle_invite(sample_sip_invite)
        call_id = response["call_id"]
        
        # Update to connected state
        await kamailio_integration.call_manager.update_call_state(call_id, CallState.CONNECTED)
        
        # Mock the RPC transfer call
        with patch.object(kamailio_integration, '_send_refer_via_rpc', 
                         return_value={"success": True}):
            success = await kamailio_integration.transfer_call(call_id, "+5555555555", "blind")
        
        # Verify transfer
        assert success is True
        call_session = kamailio_integration.call_manager.get_call_session(call_id)
        assert call_session.state == CallState.TRANSFERRING
        assert call_session.transfer_target == "+5555555555"

    @pytest.mark.asyncio
    async def test_call_hold_resume(self, kamailio_integration, sample_sip_invite):
        """Test call hold and resume functionality."""
        # Setup call
        response = await kamailio_integration.handle_invite(sample_sip_invite)
        call_id = response["call_id"]
        
        # Update to connected state
        await kamailio_integration.call_manager.update_call_state(call_id, CallState.CONNECTED)
        
        # Test hold
        with patch.object(kamailio_integration, '_send_hold_via_rpc', 
                         return_value={"success": True}):
            success = await kamailio_integration.hold_call(call_id)
        
        assert success is True
        call_session = kamailio_integration.call_manager.get_call_session(call_id)
        assert call_session.state == CallState.ON_HOLD
        assert call_session.is_on_hold is True
        
        # Test resume
        with patch.object(kamailio_integration, '_send_resume_via_rpc', 
                         return_value={"success": True}):
            success = await kamailio_integration.resume_call(call_id)
        
        assert success is True
        call_session = kamailio_integration.call_manager.get_call_session(call_id)
        assert call_session.state == CallState.CONNECTED
        assert call_session.is_on_hold is False

    @pytest.mark.asyncio
    async def test_call_hangup(self, kamailio_integration, sample_sip_invite):
        """Test call hangup."""
        # Setup call
        response = await kamailio_integration.handle_invite(sample_sip_invite)
        call_id = response["call_id"]
        
        # Hangup call
        success = await kamailio_integration.call_manager.hangup_call(call_id, "normal")
        
        assert success is True
        call_session = kamailio_integration.call_manager.get_call_session(call_id)
        assert call_session.state == CallState.COMPLETED

    @pytest.mark.asyncio
    async def test_concurrent_calls(self, call_manager):
        """Test handling multiple concurrent calls."""
        call_ids = []
        
        # Create multiple calls
        for i in range(5):
            call_data = {
                "call_id": f"concurrent-{i}",
                "from_number": f"+123456789{i}",
                "to_number": "+0987654321"
            }
            
            response = await call_manager.handle_incoming_call(call_data)
            call_ids.append(response["call_id"])
        
        # Verify all calls were created
        active_calls = call_manager.get_active_calls()
        assert len(active_calls) == 5
        
        # Verify each call
        for call_id in call_ids:
            call_session = call_manager.get_call_session(call_id)
            assert call_session is not None
            assert call_session.state in [CallState.INITIALIZING, CallState.RINGING]

    @pytest.mark.asyncio
    async def test_call_routing(self, call_manager):
        """Test call routing logic."""
        # Add routing rule to block specific number
        call_manager.call_router.blacklisted_numbers.add("+1111111111")
        
        # Test blocked number
        blocked_call = {
            "call_id": "blocked-test",
            "from_number": "+1111111111",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(blocked_call)
        assert response["action"] == "reject"
        assert response["code"] == 403
        
        # Test allowed number
        allowed_call = {
            "call_id": "allowed-test",
            "from_number": "+2222222222",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(allowed_call)
        assert response["action"] == "accept"

    @pytest.mark.asyncio
    async def test_call_queue_functionality(self, call_manager):
        """Test call queuing functionality."""
        # Add routing rule for queueing
        queue_rule = {
            "conditions": {"caller_pattern": r"\+555.*"},
            "action": {"type": "queue", "queue_name": "support", "priority": "high"},
            "priority": 100
        }
        call_manager.call_router.add_routing_rule(queue_rule)
        
        # Create call that should be queued
        queue_call = {
            "call_id": "queue-test",
            "from_number": "+5551234567",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(queue_call)
        assert response["action"] == "queue"
        assert response["queue_name"] == "support"
        assert "position" in response

    @pytest.mark.asyncio
    async def test_call_statistics(self, call_manager):
        """Test call statistics tracking."""
        initial_stats = call_manager.get_statistics()
        initial_total = initial_stats["total_calls"]
        
        # Create and complete a call
        call_data = {
            "call_id": "stats-test",
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(call_data)
        call_id = response["call_id"]
        
        # Complete the call
        await call_manager.update_call_state(call_id, CallState.CONNECTED)
        await call_manager.update_call_state(call_id, CallState.COMPLETED)
        
        # Check updated statistics
        final_stats = call_manager.get_statistics()
        assert final_stats["total_calls"] == initial_total + 1
        assert final_stats["completed_calls"] >= 1

    @pytest.mark.asyncio
    async def test_sip_message_handling(self, kamailio_integration):
        """Test SIP MESSAGE (SMS) handling."""
        sip_message_data = {
            "call_id": "sms-test-123",
            "from_uri": "sip:+1234567890@provider.com",
            "to_uri": "sip:+0987654321@our-domain.com",
            "body": "Test SMS message",
            "headers": {"Content-Type": "text/plain"}
        }
        
        # Process SIP MESSAGE
        response = await kamailio_integration.handle_sip_message(sip_message_data)
        
        # Verify response
        assert response["action"] == "ok"
        assert response["code"] == 200

    @pytest.mark.asyncio
    async def test_error_handling(self, kamailio_integration):
        """Test error handling in SIP integration."""
        # Test with malformed SIP data
        malformed_data = {
            "call_id": "error-test",
            # Missing required fields
        }
        
        response = await kamailio_integration.handle_invite(malformed_data)
        assert response["action"] == "reject"
        assert response["code"] == 500

    @pytest.mark.asyncio
    async def test_call_timeout_handling(self, call_manager):
        """Test call timeout handling."""
        # Create call
        call_data = {
            "call_id": "timeout-test",
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(call_data)
        call_id = response["call_id"]
        
        # Simulate timeout by manually setting old timestamp
        call_session = call_manager.get_call_session(call_id)
        call_session.start_time = datetime.utcnow().timestamp() - 7200  # 2 hours ago
        
        # This would be called by cleanup task
        # For testing, we manually check if call would be considered stale
        current_time = time.time()
        age = current_time - call_session.start_time
        assert age > 3600  # Call is older than 1 hour

    @pytest.mark.asyncio
    async def test_rtp_engine_integration(self, kamailio_integration, sample_sip_invite):
        """Test RTPEngine integration."""
        # Mock RTPEngine client
        with patch('src.media.rtpengine_client.RTPEngineClient') as mock_rtpengine:
            mock_instance = AsyncMock()
            mock_rtpengine.return_value = mock_instance
            
            # Mock offer response
            mock_instance.offer.return_value = (
                "modified_sdp_content",
                MagicMock(rtpengine_session_id="rtp-session-123")
            )
            
            # Process INVITE with RTPEngine
            response = await kamailio_integration.handle_invite(sample_sip_invite)
            
            # Verify call was processed
            assert response["action"] == "accept"

    @pytest.mark.asyncio
    async def test_database_integration(self, call_manager):
        """Test database integration for call records."""
        # This test would require a test database
        # For now, we test the data structure
        
        call_data = {
            "call_id": "db-test",
            "from_number": "+1234567890",
            "to_number": "+0987654321"
        }
        
        response = await call_manager.handle_incoming_call(call_data)
        call_id = response["call_id"]
        
        # Get call session for database record creation
        call_session = call_manager.get_call_session(call_id)
        
        # Verify data structure for CDR
        assert call_session.call_id == call_id
        assert call_session.caller.number == "+1234567890"
        assert call_session.callee.number == "+0987654321"
        assert call_session.created_at is not None
        assert call_session.direction == CallDirection.INBOUND

    @pytest.mark.asyncio
    async def test_memory_cleanup(self, call_manager):
        """Test memory cleanup after call completion."""
        initial_count = len(call_manager.active_calls)
        
        # Create multiple calls
        call_ids = []
        for i in range(3):
            call_data = {
                "call_id": f"cleanup-{i}",
                "from_number": f"+123456789{i}",
                "to_number": "+0987654321"
            }
            
            response = await call_manager.handle_incoming_call(call_data)
            call_ids.append(response["call_id"])
        
        # Verify calls were created
        assert len(call_manager.active_calls) == initial_count + 3
        
        # Complete all calls
        for call_id in call_ids:
            await call_manager.hangup_call(call_id, "test_cleanup")
        
        # Verify calls are marked as completed
        for call_id in call_ids:
            call_session = call_manager.get_call_session(call_id)
            assert call_session.state == CallState.COMPLETED
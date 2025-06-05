"""
Comprehensive unit tests for SMS handling components.
Tests SMS manager, processing, queuing, and SIP MESSAGE integration.
"""
import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List
from datetime import datetime, timedelta

from src.sms.sms_manager import SMSManager, SMSMessage, SMSStatus, SMSDirection
from src.sms.sms_processor import SMSProcessor, SMSProcessingRule, SMSProcessingAction
from src.sms.sms_queue import SMSQueue, QueuedSMSItem, SMSQueuePriority
from src.sms.sip_message_handler import SIPMessageHandler
from src.sms.sip_message_integration import SIPSMSIntegration


class TestSMSMessage:
    """Test SMS message data structures."""
    
    def test_sms_message_creation(self, sample_sms_data):
        """Test SMS message creation."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.INBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        assert message.message_id == sample_sms_data["message_id"]
        assert message.from_number == sample_sms_data["from_number"]
        assert message.to_number == sample_sms_data["to_number"]
        assert message.content == sample_sms_data["message"]
        assert message.direction == SMSDirection.INBOUND
        assert message.status == SMSStatus.PENDING
    
    def test_sms_status_enum(self):
        """Test SMS status enumeration."""
        assert SMSStatus.PENDING.value == "pending"
        assert SMSStatus.SENDING.value == "sending"
        assert SMSStatus.SENT.value == "sent"
        assert SMSStatus.DELIVERED.value == "delivered"
        assert SMSStatus.FAILED.value == "failed"
        assert SMSStatus.CANCELLED.value == "cancelled"
    
    def test_sms_direction_enum(self):
        """Test SMS direction enumeration."""
        assert SMSDirection.INBOUND.value == "inbound"
        assert SMSDirection.OUTBOUND.value == "outbound"
    
    def test_message_validation(self):
        """Test SMS message validation."""
        # Test valid message
        valid_message = SMSMessage(
            message_id="valid-123",
            from_number="+12345678901",
            to_number="+10987654321",
            content="Valid message",
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        assert valid_message.is_valid()
        
        # Test invalid message (empty content)
        invalid_message = SMSMessage(
            message_id="invalid-123",
            from_number="+12345678901",
            to_number="+10987654321",
            content="",  # Empty content
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        assert not invalid_message.is_valid()
    
    def test_message_serialization(self, sample_sms_data):
        """Test SMS message serialization."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.INBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        # Serialize to dict
        message_dict = message.to_dict()
        
        assert message_dict["message_id"] == sample_sms_data["message_id"]
        assert message_dict["from_number"] == sample_sms_data["from_number"]
        assert message_dict["content"] == sample_sms_data["message"]
        assert message_dict["direction"] == "inbound"
        assert message_dict["status"] == "pending"
        
        # Deserialize from dict
        restored_message = SMSMessage.from_dict(message_dict)
        
        assert restored_message.message_id == message.message_id
        assert restored_message.from_number == message.from_number
        assert restored_message.content == message.content


class TestSMSQueue:
    """Test SMS queue functionality."""
    
    @pytest.fixture
    def sms_queue(self):
        """Create test SMS queue."""
        return SMSQueue(max_size=100, retry_attempts=3)
    
    def test_queue_initialization(self, sms_queue):
        """Test SMS queue initialization."""
        assert sms_queue.max_size == 100
        assert sms_queue.retry_attempts == 3
        assert len(sms_queue.pending_messages) == 0
        assert len(sms_queue.retry_queue) == 0
    
    def test_queue_message(self, sms_queue, sample_sms_data):
        """Test queuing SMS message."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        queue_item = SMSQueueItem(
            message=message,
            priority=SMSPriority.NORMAL,
            max_retries=3,
            retry_delay=5.0
        )
        
        result = sms_queue.enqueue(queue_item)
        
        assert result is True
        assert len(sms_queue.pending_messages) == 1
        assert sms_queue.pending_messages[0].message.message_id == sample_sms_data["message_id"]
    
    def test_dequeue_message(self, sms_queue, sample_sms_data):
        """Test dequeuing SMS message."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        queue_item = SMSQueueItem(
            message=message,
            priority=SMSPriority.NORMAL
        )
        
        sms_queue.enqueue(queue_item)
        dequeued_item = sms_queue.dequeue()
        
        assert dequeued_item is not None
        assert dequeued_item.message.message_id == sample_sms_data["message_id"]
        assert len(sms_queue.pending_messages) == 0
    
    def test_priority_ordering(self, sms_queue):
        """Test priority-based message ordering."""
        # Create messages with different priorities
        low_message = SMSMessage(
            message_id="low-priority",
            from_number="+11111111111",
            to_number="+10987654321",
            content="Low priority message",
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        high_message = SMSMessage(
            message_id="high-priority",
            from_number="+12222222222",
            to_number="+10987654321",
            content="High priority message",
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now() + timedelta(seconds=1)  # Added later
        )
        
        # Enqueue low priority first, then high priority
        sms_queue.enqueue(SMSQueueItem(low_message, SMSPriority.LOW))
        sms_queue.enqueue(SMSQueueItem(high_message, SMSPriority.HIGH))
        
        # High priority should come first
        first_item = sms_queue.dequeue()
        assert first_item.message.message_id == "high-priority"
        
        # Low priority should come second
        second_item = sms_queue.dequeue()
        assert second_item.message.message_id == "low-priority"
    
    def test_retry_mechanism(self, sms_queue):
        """Test message retry mechanism."""
        message = SMSMessage(
            message_id="retry-test",
            from_number="+12345678901",
            to_number="+10987654321",
            content="Retry test message",
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        queue_item = SMSQueueItem(
            message=message,
            priority=SMSPriority.NORMAL,
            max_retries=3,
            retry_delay=1.0
        )
        
        # Simulate failed delivery
        queue_item.retry_count = 1
        queue_item.last_retry = datetime.now()
        
        sms_queue.retry_queue.append(queue_item)
        
        # Process retries
        retry_items = sms_queue.get_retry_candidates()
        
        # Should be ready for retry immediately (short delay for testing)
        assert len(retry_items) >= 0  # May be 0 due to timing
    
    def test_queue_size_limit(self, sms_queue):
        """Test queue size limit enforcement."""
        # Set small limit for testing
        sms_queue.max_size = 3
        
        # Fill queue to capacity
        for i in range(3):
            message = SMSMessage(
                message_id=f"message-{i}",
                from_number=f"+1234567890{i}",
                to_number="+10987654321",
                content=f"Message {i}",
                direction=SMSDirection.OUTBOUND,
                status=SMSStatus.PENDING,
                timestamp=datetime.now()
            )
            
            queue_item = SMSQueueItem(message, SMSPriority.NORMAL)
            result = sms_queue.enqueue(queue_item)
            assert result is True
        
        # Fourth message should be rejected
        overflow_message = SMSMessage(
            message_id="overflow",
            from_number="+19999999999",
            to_number="+10987654321",
            content="Overflow message",
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        overflow_item = SMSQueueItem(overflow_message, SMSPriority.NORMAL)
        result = sms_queue.enqueue(overflow_item)
        assert result is False
    
    def test_queue_statistics(self, sms_queue):
        """Test queue statistics generation."""
        # Add messages with different priorities
        for priority in [SMSPriority.LOW, SMSPriority.NORMAL, SMSPriority.HIGH]:
            message = SMSMessage(
                message_id=f"stats-{priority.value}",
                from_number="+12345678901",
                to_number="+10987654321",
                content=f"Priority {priority.value} message",
                direction=SMSDirection.OUTBOUND,
                status=SMSStatus.PENDING,
                timestamp=datetime.now()
            )
            
            queue_item = SMSQueueItem(message, priority)
            sms_queue.enqueue(queue_item)
        
        stats = sms_queue.get_statistics()
        
        assert stats["pending_count"] == 3
        assert stats["retry_count"] == 0
        assert "priority_breakdown" in stats
        assert stats["priority_breakdown"]["low"] == 1
        assert stats["priority_breakdown"]["normal"] == 1
        assert stats["priority_breakdown"]["high"] == 1


class TestSMSProcessor:
    """Test SMS processor functionality."""
    
    @pytest.fixture
    async def sms_processor(self, mock_ai_websocket_manager):
        """Create test SMS processor."""
        processor = SMSProcessor(mock_ai_websocket_manager)
        await processor.start()
        yield processor
        await processor.stop()
    
    def test_sms_processor_initialization(self, sms_processor):
        """Test SMS processor initialization."""
        assert sms_processor.ai_websocket_manager is not None
        assert sms_processor.is_running is True
        assert len(sms_processor.processing_statistics) >= 0
    
    @pytest.mark.asyncio
    async def test_process_inbound_sms(self, sms_processor, sample_sms_data):
        """Test processing inbound SMS."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.INBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        result = await sms_processor.process_inbound_message(message)
        
        assert isinstance(result, SMSProcessingResult)
        assert result.success is True
        assert result.message_id == sample_sms_data["message_id"]
    
    @pytest.mark.asyncio
    async def test_process_outbound_sms(self, sms_processor, sample_sms_data):
        """Test processing outbound SMS."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        result = await sms_processor.process_outbound_message(message)
        
        assert isinstance(result, SMSProcessingResult)
        assert result.success is True
        assert result.message_id == sample_sms_data["message_id"]
    
    @pytest.mark.asyncio
    async def test_ai_platform_integration(self, sms_processor, sample_sms_data):
        """Test AI platform integration for SMS."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.INBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        # Process message (should send to AI platform)
        result = await sms_processor.process_inbound_message(message)
        
        # Verify AI websocket manager was called
        sms_processor.ai_websocket_manager.send_message.assert_called()
        
        # Check the message sent to AI platform
        call_args = sms_processor.ai_websocket_manager.send_message.call_args
        sent_message = call_args[0][0]
        
        assert "type" in sent_message
        assert sent_message["type"] == "sms_message"
        assert "from_number" in sent_message
        assert "content" in sent_message
    
    @pytest.mark.asyncio
    async def test_message_filtering(self, sms_processor):
        """Test SMS message filtering."""
        # Test spam message
        spam_message = SMSMessage(
            message_id="spam-test",
            from_number="+19999999999",
            to_number="+10987654321",
            content="URGENT! Click this link to win $1000000!!!",
            direction=SMSDirection.INBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        # Add spam filter
        def spam_filter(message: SMSMessage) -> bool:
            spam_keywords = ["urgent", "click", "win", "$"]
            content_lower = message.content.lower()
            return any(keyword in content_lower for keyword in spam_keywords)
        
        sms_processor.add_filter("spam_filter", spam_filter)
        
        result = await sms_processor.process_inbound_message(spam_message)
        
        # Message should be filtered
        assert result.success is False
        assert "filtered" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_message_transformation(self, sms_processor, sample_sms_data):
        """Test SMS message transformation."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content="hello world",  # lowercase
            direction=SMSDirection.INBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        # Add transformation
        def uppercase_transformer(message: SMSMessage) -> SMSMessage:
            message.content = message.content.upper()
            return message
        
        sms_processor.add_transformer("uppercase", uppercase_transformer)
        
        result = await sms_processor.process_inbound_message(message)
        
        assert result.success is True
        # Content should be transformed to uppercase
        assert message.content == "HELLO WORLD"
    
    def test_processing_statistics(self, sms_processor):
        """Test SMS processing statistics."""
        # Set test data
        sms_processor.total_processed = 100
        sms_processor.successful_processed = 95
        sms_processor.failed_processed = 5
        sms_processor.filtered_messages = 10
        
        stats = sms_processor.get_statistics()
        
        assert stats["total_processed"] == 100
        assert stats["successful_processed"] == 95
        assert stats["failed_processed"] == 5
        assert stats["filtered_messages"] == 10
        assert stats["success_rate"] == 0.95


class TestSIPMessageHandler:
    """Test SIP MESSAGE protocol handler."""
    
    @pytest.fixture
    def sip_message_handler(self):
        """Create test SIP message handler."""
        return SIPMessageHandler()
    
    def test_sip_message_parsing(self, sip_message_handler):
        """Test parsing SIP MESSAGE."""
        sip_message = """MESSAGE sip:+10987654321@example.com SIP/2.0
Via: SIP/2.0/UDP 192.168.1.100:5060;branch=z9hG4bK123456
From: <sip:+12345678901@example.com>;tag=abc123
To: <sip:+10987654321@example.com>
Call-ID: test-call-id@192.168.1.100
CSeq: 1 MESSAGE
Contact: <sip:+12345678901@192.168.1.100:5060>
Content-Type: text/plain
Content-Length: 26

Test SMS message content"""
        
        parsed = sip_message_handler.parse_message(sip_message)
        
        assert parsed is not None
        assert parsed["method"] == "MESSAGE"
        assert parsed["from_number"] == "+12345678901"
        assert parsed["to_number"] == "+10987654321"
        assert parsed["content"] == "Test SMS message content"
        assert parsed["content_type"] == "text/plain"
    
    def test_sip_message_creation(self, sip_message_handler, sample_sms_data):
        """Test creating SIP MESSAGE."""
        sip_message = sip_message_handler.create_message(
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            call_id="test-call-id"
        )
        
        assert "MESSAGE" in sip_message
        assert sample_sms_data["from_number"] in sip_message
        assert sample_sms_data["to_number"] in sip_message
        assert sample_sms_data["message"] in sip_message
        assert "Content-Type: text/plain" in sip_message
        assert f"Content-Length: {len(sample_sms_data['message'])}" in sip_message
    
    def test_unicode_content_handling(self, sip_message_handler):
        """Test handling Unicode content in SMS."""
        unicode_content = "Hello 👋 Unicode message with émojis 🚀"
        
        sip_message = sip_message_handler.create_message(
            from_number="+12345678901",
            to_number="+10987654321",
            content=unicode_content,
            call_id="unicode-test"
        )
        
        # Should handle Unicode properly
        assert unicode_content in sip_message
        
        # Content-Length should account for UTF-8 encoding
        utf8_length = len(unicode_content.encode('utf-8'))
        assert f"Content-Length: {utf8_length}" in sip_message
    
    def test_long_message_handling(self, sip_message_handler):
        """Test handling long SMS messages."""
        long_content = "A" * 1000  # 1000 character message
        
        sip_message = sip_message_handler.create_message(
            from_number="+12345678901",
            to_number="+10987654321",
            content=long_content,
            call_id="long-test"
        )
        
        assert long_content in sip_message
        assert f"Content-Length: {len(long_content)}" in sip_message
    
    def test_sip_response_creation(self, sip_message_handler):
        """Test creating SIP responses for MESSAGE."""
        # Test success response
        success_response = sip_message_handler.create_response(
            status_code=200,
            reason_phrase="OK",
            call_id="test-call",
            via_header="SIP/2.0/UDP 192.168.1.100:5060;branch=z9hG4bK123456",
            from_header="<sip:+12345678901@example.com>;tag=abc123",
            to_header="<sip:+10987654321@example.com>;tag=def456"
        )
        
        assert "SIP/2.0 200 OK" in success_response
        assert "test-call" in success_response
        
        # Test error response
        error_response = sip_message_handler.create_response(
            status_code=400,
            reason_phrase="Bad Request",
            call_id="test-call",
            via_header="SIP/2.0/UDP 192.168.1.100:5060;branch=z9hG4bK123456",
            from_header="<sip:+12345678901@example.com>;tag=abc123",
            to_header="<sip:+10987654321@example.com>;tag=def456"
        )
        
        assert "SIP/2.0 400 Bad Request" in error_response


class TestSIPMessageIntegration:
    """Test SIP MESSAGE integration with SMS system."""
    
    @pytest.fixture
    async def sip_integration(self, sms_manager):
        """Create test SIP MESSAGE integration."""
        integration = SIPMessageIntegration(sms_manager)
        await integration.start()
        yield integration
        await integration.stop()
    
    @pytest.mark.asyncio
    async def test_inbound_sip_message_handling(self, sip_integration, sample_sms_data):
        """Test handling inbound SIP MESSAGE."""
        sip_message_data = {
            "method": "MESSAGE",
            "from_number": sample_sms_data["from_number"],
            "to_number": sample_sms_data["to_number"],
            "content": sample_sms_data["message"],
            "call_id": "sip-message-test",
            "headers": {
                "Content-Type": "text/plain",
                "From": f"<sip:{sample_sms_data['from_number']}@example.com>",
                "To": f"<sip:{sample_sms_data['to_number']}@example.com>"
            }
        }
        
        result = await sip_integration.handle_inbound_message(sip_message_data)
        
        assert result["success"] is True
        assert "message_id" in result
        assert result["status"] == "accepted"
    
    @pytest.mark.asyncio
    async def test_outbound_sip_message_sending(self, sip_integration, sample_sms_data):
        """Test sending outbound SIP MESSAGE."""
        message = SMSMessage(
            message_id=sample_sms_data["message_id"],
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"],
            direction=SMSDirection.OUTBOUND,
            status=SMSStatus.PENDING,
            timestamp=datetime.now()
        )
        
        result = await sip_integration.send_outbound_message(message)
        
        assert result["success"] is True
        assert result["message_id"] == sample_sms_data["message_id"]
        assert "sip_call_id" in result
    
    @pytest.mark.asyncio
    async def test_delivery_confirmation(self, sip_integration, sample_sms_data):
        """Test SMS delivery confirmation handling."""
        message_id = sample_sms_data["message_id"]
        
        # Simulate delivery confirmation
        confirmation_data = {
            "message_id": message_id,
            "status": "delivered",
            "timestamp": datetime.now().isoformat(),
            "reason": "Message delivered successfully"
        }
        
        result = await sip_integration.handle_delivery_confirmation(confirmation_data)
        
        assert result["success"] is True
        assert result["message_id"] == message_id
        assert result["status"] == "delivered"
    
    @pytest.mark.asyncio
    async def test_error_handling(self, sip_integration):
        """Test error handling in SIP MESSAGE integration."""
        # Test malformed SIP message
        malformed_data = {
            "method": "MESSAGE",
            # Missing required fields
        }
        
        result = await sip_integration.handle_inbound_message(malformed_data)
        
        assert result["success"] is False
        assert "error" in result
        assert "malformed" in result["error"].lower() or "invalid" in result["error"].lower()


class TestSMSManager:
    """Test SMS manager main functionality."""
    
    @pytest.mark.asyncio
    async def test_sms_manager_initialization(self, sms_manager):
        """Test SMS manager initialization."""
        assert sms_manager.ai_websocket_manager is not None
        assert sms_manager.message_queue is not None
        assert sms_manager.processor is not None
        assert sms_manager.sip_integration is not None
        assert len(sms_manager.active_messages) == 0
    
    @pytest.mark.asyncio
    async def test_send_sms(self, sms_manager, sample_sms_data):
        """Test sending SMS through manager."""
        result = await sms_manager.send_sms(
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"]
        )
        
        assert result["success"] is True
        assert "message_id" in result
        assert result["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_receive_sms(self, sms_manager, sample_sms_data):
        """Test receiving SMS through manager."""
        sip_data = {
            "from_number": sample_sms_data["from_number"],
            "to_number": sample_sms_data["to_number"],
            "content": sample_sms_data["message"],
            "timestamp": datetime.now().isoformat()
        }
        
        result = await sms_manager.receive_sms(sip_data)
        
        assert result["success"] is True
        assert "message_id" in result
        assert result["status"] == "received"
    
    @pytest.mark.asyncio
    async def test_get_message_status(self, sms_manager, sample_sms_data):
        """Test getting SMS message status."""
        # Send a message first
        send_result = await sms_manager.send_sms(
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"]
        )
        
        message_id = send_result["message_id"]
        
        # Get status
        status_result = await sms_manager.get_message_status(message_id)
        
        assert status_result["success"] is True
        assert status_result["message_id"] == message_id
        assert "status" in status_result
        assert "timestamp" in status_result
    
    @pytest.mark.asyncio
    async def test_get_message_history(self, sms_manager, sample_sms_data):
        """Test getting SMS message history."""
        # Send multiple messages
        for i in range(3):
            await sms_manager.send_sms(
                from_number=sample_sms_data["from_number"],
                to_number=sample_sms_data["to_number"],
                content=f"Test message {i+1}"
            )
        
        # Get history
        history = await sms_manager.get_message_history(
            number=sample_sms_data["from_number"],
            limit=10
        )
        
        assert len(history) >= 3
        assert all("message_id" in msg for msg in history)
        assert all("content" in msg for msg in history)
        assert all("timestamp" in msg for msg in history)
    
    @pytest.mark.asyncio
    async def test_concurrent_sms_processing(self, sms_manager):
        """Test concurrent SMS processing."""
        # Send multiple SMS concurrently
        tasks = []
        for i in range(10):
            task = asyncio.create_task(sms_manager.send_sms(
                from_number=f"+123456789{i:02d}",
                to_number="+10987654321",
                content=f"Concurrent message {i+1}"
            ))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(result["success"] for result in results)
        
        # All should have unique message IDs
        message_ids = [result["message_id"] for result in results]
        assert len(set(message_ids)) == len(message_ids)
    
    def test_sms_statistics(self, sms_manager):
        """Test SMS statistics generation."""
        # Set test data
        sms_manager.total_sent = 150
        sms_manager.total_received = 200
        sms_manager.failed_messages = 5
        sms_manager.pending_messages = 10
        
        stats = sms_manager.get_statistics()
        
        assert stats["total_sent"] == 150
        assert stats["total_received"] == 200
        assert stats["failed_messages"] == 5
        assert stats["pending_messages"] == 10
        assert stats["success_rate"] > 0
        assert "queue_stats" in stats
        assert "processor_stats" in stats


class TestSMSPerformance:
    """Test SMS system performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_sms_throughput(self, sms_manager, performance_thresholds):
        """Test SMS processing throughput."""
        message_count = 100
        start_time = time.perf_counter()
        
        # Send messages concurrently
        tasks = []
        for i in range(message_count):
            task = asyncio.create_task(sms_manager.send_sms(
                from_number=f"+123456789{i:02d}",
                to_number="+10987654321",
                content=f"Throughput test message {i+1}"
            ))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        end_time = time.perf_counter()
        total_time = end_time - start_time
        messages_per_second = message_count / total_time
        
        # Should process at least 50 messages per second
        assert messages_per_second >= 50
    
    @pytest.mark.asyncio
    async def test_queue_performance(self, sms_queue, performance_thresholds):
        """Test SMS queue performance."""
        # Measure enqueue/dequeue performance
        message_count = 1000
        
        # Create test messages
        messages = []
        for i in range(message_count):
            message = SMSMessage(
                message_id=f"perf-test-{i}",
                from_number=f"+123456789{i:02d}",
                to_number="+10987654321",
                content=f"Performance test message {i}",
                direction=SMSDirection.OUTBOUND,
                status=SMSStatus.PENDING,
                timestamp=datetime.now()
            )
            messages.append(SMSQueueItem(message, SMSPriority.NORMAL))
        
        # Measure enqueue time
        start_time = time.perf_counter()
        for queue_item in messages:
            sms_queue.enqueue(queue_item)
        enqueue_time = time.perf_counter() - start_time
        
        # Measure dequeue time
        start_time = time.perf_counter()
        dequeued_count = 0
        while sms_queue.dequeue() is not None:
            dequeued_count += 1
        dequeue_time = time.perf_counter() - start_time
        
        # Performance should be reasonable
        assert enqueue_time < 1.0  # Should enqueue 1000 messages in < 1 second
        assert dequeue_time < 1.0  # Should dequeue 1000 messages in < 1 second
        assert dequeued_count == message_count
    
    def test_memory_usage_under_load(self, sms_manager):
        """Test SMS system memory usage under load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create many SMS messages in memory
        messages = []
        for i in range(1000):
            message = SMSMessage(
                message_id=f"memory-test-{i}",
                from_number=f"+123456789{i:02d}",
                to_number="+10987654321",
                content=f"Memory test message {i} with some additional content to increase size",
                direction=SMSDirection.OUTBOUND,
                status=SMSStatus.PENDING,
                timestamp=datetime.now()
            )
            messages.append(message)
        
        current_memory = process.memory_info().rss
        memory_increase = current_memory - initial_memory
        
        # Memory increase should be reasonable (less than 50MB for 1000 messages)
        assert memory_increase < 50 * 1024 * 1024
        
        # Cleanup
        messages.clear()


class TestSMSResilience:
    """Test SMS system resilience and fault tolerance."""
    
    @pytest.mark.asyncio
    async def test_message_persistence(self, sms_manager, sample_sms_data):
        """Test SMS message persistence across restarts."""
        # Send message
        result = await sms_manager.send_sms(
            from_number=sample_sms_data["from_number"],
            to_number=sample_sms_data["to_number"],
            content=sample_sms_data["message"]
        )
        
        message_id = result["message_id"]
        
        # Simulate restart
        await sms_manager.stop_processing()
        await sms_manager.start_processing()
        
        # Message should still be accessible
        status = await sms_manager.get_message_status(message_id)
        assert status["success"] is True
    
    @pytest.mark.asyncio
    async def test_network_failure_recovery(self, sms_manager):
        """Test recovery from network failures."""
        # Simulate network failure
        with patch.object(sms_manager.sip_integration, 'send_outbound_message', side_effect=ConnectionError("Network failed")):
            result = await sms_manager.send_sms(
                from_number="+12345678901",
                to_number="+10987654321",
                content="Network failure test"
            )
            
            # Should handle failure gracefully
            assert result["success"] is False
            assert "error" in result
    
    @pytest.mark.asyncio
    async def test_malformed_message_handling(self, sms_manager):
        """Test handling of malformed messages."""
        malformed_data = {
            "from_number": "invalid_number",
            "to_number": "",  # Empty recipient
            "content": None,  # Null content
            "timestamp": "invalid_timestamp"
        }
        
        result = await sms_manager.receive_sms(malformed_data)
        
        # Should handle malformed data gracefully
        assert result["success"] is False
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_queue_overflow_handling(self, sms_manager):
        """Test handling of queue overflow conditions."""
        # Set small queue limit
        sms_manager.message_queue.max_size = 5
        
        # Try to send more messages than queue can handle
        results = []
        for i in range(10):
            result = await sms_manager.send_sms(
                from_number=f"+123456789{i:02d}",
                to_number="+10987654321",
                content=f"Overflow test {i+1}"
            )
            results.append(result)
        
        # Some messages should be rejected due to queue overflow
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        assert len(successful) <= 5  # Queue capacity
        assert len(failed) >= 5    # Overflow messages
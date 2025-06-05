"""Comprehensive SMS testing suite for SIP server."""
import pytest
import asyncio
import time
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any, Optional

# Import SMS modules
from src.sms.sms_manager import SMSManager
from src.sms.sms_processor import SMSProcessor
from src.sms.sms_queue import SMSQueue
from src.sms.sip_message_handler import SIPMessageHandler
from src.models.schemas import SMSInfo, SMSSend


class TestSMSManager:
    """Test suite for SMS Manager functionality."""
    
    @pytest.fixture
    async def sms_manager(self):
        """Create SMS manager instance."""
        manager = SMSManager()
        await manager.initialize()
        yield manager
        await manager.cleanup()
    
    @pytest.fixture
    def sample_sms_data(self):
        """Sample SMS data for testing."""
        return {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Hello from SIP server test!",
            "webhook_url": "https://example.com/webhook"
        }
    
    @pytest.fixture
    def sample_sms_info(self):
        """Sample SMS info object."""
        return SMSInfo(
            message_id="sms-test-123",
            from_number="+1234567890",
            to_number="+0987654321",
            message="Test message",
            status="pending",
            direction="outbound",
            timestamp=datetime.utcnow(),
            segments=1
        )
    
    @pytest.mark.asyncio
    async def test_sms_manager_initialization(self, sms_manager):
        """Test SMS manager initialization."""
        assert sms_manager is not None
        assert sms_manager.is_initialized is True
        assert hasattr(sms_manager, 'queue')
        assert hasattr(sms_manager, 'processor')
    
    @pytest.mark.asyncio
    async def test_send_sms_basic(self, sms_manager, sample_sms_data):
        """Test basic SMS sending functionality."""
        # Mock the SIP message sending
        with patch.object(sms_manager, '_send_sip_message', return_value=True):
            result = await sms_manager.send_sms(
                from_number=sample_sms_data["from_number"],
                to_number=sample_sms_data["to_number"],
                message=sample_sms_data["message"]
            )
        
        assert result is not None
        assert result.from_number == sample_sms_data["from_number"]
        assert result.to_number == sample_sms_data["to_number"]
        assert result.message == sample_sms_data["message"]
        assert result.status == "sent"
        assert result.direction == "outbound"
        assert result.message_id is not None
    
    @pytest.mark.asyncio
    async def test_send_sms_with_webhook(self, sms_manager, sample_sms_data):
        """Test SMS sending with webhook URL."""
        with patch.object(sms_manager, '_send_sip_message', return_value=True):
            result = await sms_manager.send_sms(
                from_number=sample_sms_data["from_number"],
                to_number=sample_sms_data["to_number"],
                message=sample_sms_data["message"],
                webhook_url=sample_sms_data["webhook_url"]
            )
        
        assert result.webhook_url == sample_sms_data["webhook_url"]
    
    @pytest.mark.asyncio
    async def test_send_long_sms(self, sms_manager):
        """Test sending long SMS that requires segmentation."""
        long_message = "A" * 500  # 500 characters
        
        with patch.object(sms_manager, '_send_sip_message', return_value=True):
            result = await sms_manager.send_sms(
                from_number="+1234567890",
                to_number="+0987654321",
                message=long_message
            )
        
        assert result.segments > 1
        assert result.message == long_message
    
    @pytest.mark.asyncio
    async def test_send_unicode_sms(self, sms_manager):
        """Test sending SMS with Unicode characters."""
        unicode_message = "Hello 🌟 世界 测试 émojis!"
        
        with patch.object(sms_manager, '_send_sip_message', return_value=True):
            result = await sms_manager.send_sms(
                from_number="+1234567890",
                to_number="+0987654321",
                message=unicode_message
            )
        
        assert result.message == unicode_message
        assert result.status == "sent"
    
    @pytest.mark.asyncio
    async def test_get_message_status(self, sms_manager, sample_sms_info):
        """Test retrieving SMS message status."""
        # Mock database lookup
        with patch.object(sms_manager, '_get_message_from_db', return_value=sample_sms_info):
            status = await sms_manager.get_message_status(sample_sms_info.message_id)
        
        assert status is not None
        assert status.message_id == sample_sms_info.message_id
        assert status.status == sample_sms_info.status
    
    @pytest.mark.asyncio
    async def test_get_message_history(self, sms_manager):
        """Test retrieving SMS message history."""
        # Mock database query
        mock_messages = [
            SMSInfo(
                message_id=f"msg-{i}",
                from_number="+1234567890",
                to_number="+0987654321",
                message=f"Test message {i}",
                status="sent",
                direction="outbound",
                timestamp=datetime.utcnow(),
                segments=1
            ) for i in range(5)
        ]
        
        with patch.object(sms_manager, '_get_messages_from_db', return_value=mock_messages):
            history = await sms_manager.get_message_history(
                number="+1234567890",
                limit=5
            )
        
        assert len(history) == 5
        assert all(msg.from_number == "+1234567890" for msg in history)
    
    @pytest.mark.asyncio
    async def test_retry_failed_message(self, sms_manager):
        """Test retrying a failed SMS message."""
        failed_message = SMSInfo(
            message_id="failed-msg-123",
            from_number="+1234567890",
            to_number="+0987654321",
            message="Failed message",
            status="failed",
            direction="outbound",
            timestamp=datetime.utcnow(),
            segments=1
        )
        
        with patch.object(sms_manager, '_get_message_from_db', return_value=failed_message):
            with patch.object(sms_manager, '_send_sip_message', return_value=True):
                success = await sms_manager.retry_failed_message("failed-msg-123")
        
        assert success is True
    
    @pytest.mark.asyncio
    async def test_cancel_message(self, sms_manager):
        """Test cancelling a pending SMS message."""
        pending_message = SMSInfo(
            message_id="pending-msg-123",
            from_number="+1234567890",
            to_number="+0987654321",
            message="Pending message",
            status="pending",
            direction="outbound",
            timestamp=datetime.utcnow(),
            segments=1
        )
        
        with patch.object(sms_manager, '_get_message_from_db', return_value=pending_message):
            with patch.object(sms_manager, '_update_message_status') as mock_update:
                success = await sms_manager.cancel_message("pending-msg-123")
        
        assert success is True
        mock_update.assert_called_with("pending-msg-123", "cancelled")
    
    @pytest.mark.asyncio
    async def test_bulk_sms_send(self, sms_manager):
        """Test bulk SMS sending."""
        bulk_data = {
            "from_number": "+1234567890",
            "messages": [
                {"to_number": "+0987654321", "message": "Message 1"},
                {"to_number": "+0987654322", "message": "Message 2"},
                {"to_number": "+0987654323", "message": "Message 3"}
            ]
        }
        
        with patch.object(sms_manager, '_send_sip_message', return_value=True):
            results = await sms_manager.send_bulk_sms(bulk_data)
        
        assert len(results) == 3
        assert all(result.status == "sent" for result in results)
        assert all(result.from_number == "+1234567890" for result in results)
    
    @pytest.mark.asyncio
    async def test_sms_statistics(self, sms_manager):
        """Test SMS statistics retrieval."""
        mock_stats = {
            "total_messages": 100,
            "sent_messages": 95,
            "failed_messages": 5,
            "pending_messages": 0,
            "success_rate": 0.95
        }
        
        with patch.object(sms_manager, '_get_statistics_from_db', return_value=mock_stats):
            stats = await sms_manager.get_statistics()
        
        assert stats["total_messages"] == 100
        assert stats["success_rate"] == 0.95
    
    @pytest.mark.asyncio
    async def test_phone_number_validation(self, sms_manager):
        """Test phone number validation."""
        valid_numbers = ["+1234567890", "+44123456789", "+861234567890"]
        invalid_numbers = ["123", "invalid", "+", ""]
        
        for number in valid_numbers:
            assert sms_manager._validate_phone_number(number) is True
        
        for number in invalid_numbers:
            assert sms_manager._validate_phone_number(number) is False
    
    @pytest.mark.asyncio
    async def test_message_length_validation(self, sms_manager):
        """Test message length validation and segmentation."""
        # Normal message
        normal_msg = "Short message"
        segments = sms_manager._calculate_segments(normal_msg)
        assert segments == 1
        
        # Long message
        long_msg = "A" * 500
        segments = sms_manager._calculate_segments(long_msg)
        assert segments > 1
        
        # Unicode message
        unicode_msg = "Hello 世界" * 50
        segments = sms_manager._calculate_segments(unicode_msg)
        assert segments >= 1


class TestSMSProcessor:
    """Test suite for SMS Processor functionality."""
    
    @pytest.fixture
    def sms_processor(self):
        """Create SMS processor instance."""
        return SMSProcessor()
    
    @pytest.fixture
    def sample_incoming_sms(self):
        """Sample incoming SMS data."""
        return {
            "from_uri": "sip:+1234567890@provider.com",
            "to_uri": "sip:+0987654321@our-domain.com",
            "body": "Hello from external sender!",
            "headers": {
                "Content-Type": "text/plain",
                "Content-Length": "25"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @pytest.mark.asyncio
    async def test_process_incoming_sms(self, sms_processor, sample_incoming_sms):
        """Test processing incoming SMS messages."""
        result = await sms_processor.process_incoming_message(sample_incoming_sms)
        
        assert result is not None
        assert result.direction == "inbound"
        assert result.from_number == "+1234567890"
        assert result.to_number == "+0987654321"
        assert result.message == "Hello from external sender!"
        assert result.status == "received"
    
    @pytest.mark.asyncio
    async def test_process_delivery_receipt(self, sms_processor):
        """Test processing SMS delivery receipts."""
        delivery_receipt = {
            "from_uri": "sip:+0987654321@provider.com",
            "to_uri": "sip:+1234567890@our-domain.com",
            "body": "Message delivered successfully",
            "headers": {
                "Content-Type": "text/plain",
                "X-SMS-Status": "delivered",
                "X-Message-ID": "msg-123"
            }
        }
        
        with patch.object(sms_processor, '_update_message_delivery_status') as mock_update:
            await sms_processor.process_delivery_receipt(delivery_receipt)
        
        mock_update.assert_called_with("msg-123", "delivered")
    
    @pytest.mark.asyncio
    async def test_message_filtering(self, sms_processor):
        """Test SMS message filtering and spam detection."""
        spam_messages = [
            "URGENT: You've won $1000000! Click here now!",
            "Free money! No strings attached!",
            "Call now to claim your prize!"
        ]
        
        legitimate_messages = [
            "Hi, this is John. Can we meet tomorrow?",
            "Your appointment is confirmed for 3 PM",
            "Thank you for your order #12345"
        ]
        
        for msg in spam_messages:
            is_spam = sms_processor._detect_spam(msg)
            assert is_spam is True
        
        for msg in legitimate_messages:
            is_spam = sms_processor._detect_spam(msg)
            assert is_spam is False
    
    @pytest.mark.asyncio
    async def test_auto_reply_functionality(self, sms_processor):
        """Test auto-reply functionality."""
        auto_reply_config = {
            "enabled": True,
            "keyword_replies": {
                "HELP": "For assistance, call +1234567890",
                "HOURS": "We're open Mon-Fri 9AM-5PM",
                "STOP": "You've been unsubscribed"
            },
            "default_reply": "Thank you for your message. We'll get back to you soon."
        }
        
        sms_processor.configure_auto_reply(auto_reply_config)
        
        # Test keyword replies
        help_reply = await sms_processor.generate_auto_reply("HELP")
        assert help_reply == "For assistance, call +1234567890"
        
        hours_reply = await sms_processor.generate_auto_reply("HOURS")
        assert hours_reply == "We're open Mon-Fri 9AM-5PM"
        
        # Test default reply
        default_reply = await sms_processor.generate_auto_reply("Random message")
        assert default_reply == "Thank you for your message. We'll get back to you soon."
    
    @pytest.mark.asyncio
    async def test_webhook_delivery(self, sms_processor, sample_incoming_sms):
        """Test webhook delivery for incoming messages."""
        webhook_url = "https://example.com/webhook"
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response
            
            success = await sms_processor.deliver_webhook(sample_incoming_sms, webhook_url)
        
        assert success is True
        mock_post.assert_called_once()


class TestSMSQueue:
    """Test suite for SMS Queue functionality."""
    
    @pytest.fixture
    async def sms_queue(self):
        """Create SMS queue instance."""
        queue = SMSQueue(max_size=100)
        await queue.start()
        yield queue
        await queue.stop()
    
    @pytest.fixture
    def sample_sms_tasks(self):
        """Sample SMS tasks for queue testing."""
        return [
            {
                "message_id": f"msg-{i}",
                "from_number": "+1234567890",
                "to_number": f"+098765432{i}",
                "message": f"Test message {i}",
                "priority": "normal",
                "retry_count": 0,
                "max_retries": 3
            } for i in range(5)
        ]
    
    @pytest.mark.asyncio
    async def test_queue_initialization(self, sms_queue):
        """Test SMS queue initialization."""
        assert sms_queue.is_running is True
        assert sms_queue.size() == 0
        assert sms_queue.max_size == 100
    
    @pytest.mark.asyncio
    async def test_enqueue_messages(self, sms_queue, sample_sms_tasks):
        """Test enqueueing SMS messages."""
        for task in sample_sms_tasks:
            await sms_queue.enqueue(task)
        
        assert sms_queue.size() == len(sample_sms_tasks)
    
    @pytest.mark.asyncio
    async def test_dequeue_messages(self, sms_queue, sample_sms_tasks):
        """Test dequeueing SMS messages."""
        # Enqueue messages
        for task in sample_sms_tasks:
            await sms_queue.enqueue(task)
        
        # Dequeue messages
        dequeued_tasks = []
        for _ in range(len(sample_sms_tasks)):
            task = await sms_queue.dequeue()
            if task:
                dequeued_tasks.append(task)
        
        assert len(dequeued_tasks) == len(sample_sms_tasks)
        assert sms_queue.size() == 0
    
    @pytest.mark.asyncio
    async def test_priority_queue_ordering(self, sms_queue):
        """Test priority queue message ordering."""
        # Add messages with different priorities
        high_priority_task = {
            "message_id": "high-pri",
            "priority": "high",
            "from_number": "+1111111111",
            "to_number": "+2222222222",
            "message": "High priority message"
        }
        
        normal_priority_task = {
            "message_id": "normal-pri",
            "priority": "normal",
            "from_number": "+3333333333",
            "to_number": "+4444444444",
            "message": "Normal priority message"
        }
        
        low_priority_task = {
            "message_id": "low-pri",
            "priority": "low",
            "from_number": "+5555555555",
            "to_number": "+6666666666",
            "message": "Low priority message"
        }
        
        # Enqueue in mixed order
        await sms_queue.enqueue(normal_priority_task)
        await sms_queue.enqueue(low_priority_task)
        await sms_queue.enqueue(high_priority_task)
        
        # Dequeue and verify order
        first_task = await sms_queue.dequeue()
        assert first_task["message_id"] == "high-pri"
        
        second_task = await sms_queue.dequeue()
        assert second_task["message_id"] == "normal-pri"
        
        third_task = await sms_queue.dequeue()
        assert third_task["message_id"] == "low-pri"
    
    @pytest.mark.asyncio
    async def test_queue_retry_mechanism(self, sms_queue):
        """Test queue retry mechanism for failed messages."""
        retry_task = {
            "message_id": "retry-test",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Retry test message",
            "retry_count": 0,
            "max_retries": 3
        }
        
        await sms_queue.enqueue(retry_task)
        
        # Simulate processing failure and retry
        task = await sms_queue.dequeue()
        assert task["retry_count"] == 0
        
        # Mark as failed and retry
        await sms_queue.retry_task(task)
        
        # Dequeue retried task
        retried_task = await sms_queue.dequeue()
        assert retried_task["retry_count"] == 1
        assert retried_task["message_id"] == "retry-test"
    
    @pytest.mark.asyncio
    async def test_queue_max_capacity(self, sms_queue):
        """Test queue maximum capacity handling."""
        # Fill queue to capacity
        for i in range(sms_queue.max_size):
            task = {
                "message_id": f"capacity-test-{i}",
                "from_number": "+1234567890",
                "to_number": "+0987654321",
                "message": f"Capacity test {i}"
            }
            await sms_queue.enqueue(task)
        
        # Try to add one more (should handle gracefully)
        overflow_task = {
            "message_id": "overflow-test",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Overflow test"
        }
        
        result = await sms_queue.enqueue(overflow_task)
        # Should either reject or handle overflow gracefully
        assert result is not None  # Implementation dependent
    
    @pytest.mark.asyncio
    async def test_queue_statistics(self, sms_queue, sample_sms_tasks):
        """Test queue statistics tracking."""
        # Enqueue some tasks
        for task in sample_sms_tasks[:3]:
            await sms_queue.enqueue(task)
        
        stats = sms_queue.get_statistics()
        
        assert stats["current_size"] == 3
        assert stats["total_enqueued"] >= 3
        assert "processing_rate" in stats
        assert "average_wait_time" in stats


class TestSIPMessageHandler:
    """Test suite for SIP MESSAGE handler functionality."""
    
    @pytest.fixture
    def sip_message_handler(self):
        """Create SIP MESSAGE handler instance."""
        return SIPMessageHandler()
    
    @pytest.fixture
    def sample_sip_message(self):
        """Sample SIP MESSAGE data."""
        return {
            "method": "MESSAGE",
            "from_uri": "sip:+1234567890@provider.com",
            "to_uri": "sip:+0987654321@our-domain.com",
            "call_id": "msg-call-id-123",
            "cseq": "1 MESSAGE",
            "headers": {
                "Content-Type": "text/plain",
                "Content-Length": "11"
            },
            "body": "Hello World"
        }
    
    @pytest.mark.asyncio
    async def test_parse_sip_message(self, sip_message_handler, sample_sip_message):
        """Test parsing SIP MESSAGE requests."""
        parsed = await sip_message_handler.parse_message(sample_sip_message)
        
        assert parsed is not None
        assert parsed["from_number"] == "+1234567890"
        assert parsed["to_number"] == "+0987654321"
        assert parsed["message_body"] == "Hello World"
        assert parsed["content_type"] == "text/plain"
    
    @pytest.mark.asyncio
    async def test_generate_sip_message(self, sip_message_handler):
        """Test generating SIP MESSAGE requests."""
        message_data = {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "Test SIP MESSAGE",
            "message_id": "test-msg-123"
        }
        
        sip_message = await sip_message_handler.generate_message(message_data)
        
        assert "MESSAGE" in sip_message
        assert "+1234567890" in sip_message
        assert "+0987654321" in sip_message
        assert "Test SIP MESSAGE" in sip_message
        assert "Content-Type: text/plain" in sip_message
    
    @pytest.mark.asyncio
    async def test_sip_message_response_handling(self, sip_message_handler):
        """Test handling SIP MESSAGE responses."""
        success_response = {
            "status_code": 200,
            "reason_phrase": "OK",
            "headers": {
                "Call-ID": "msg-call-id-123"
            }
        }
        
        error_response = {
            "status_code": 404,
            "reason_phrase": "Not Found",
            "headers": {
                "Call-ID": "msg-call-id-456"
            }
        }
        
        # Test success response
        success_result = await sip_message_handler.handle_response(success_response)
        assert success_result["status"] == "delivered"
        
        # Test error response
        error_result = await sip_message_handler.handle_response(error_response)
        assert error_result["status"] == "failed"
    
    @pytest.mark.asyncio
    async def test_multipart_message_handling(self, sip_message_handler):
        """Test handling multipart SMS messages."""
        multipart_data = {
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "message": "A" * 500,  # Long message requiring segmentation
            "message_id": "multipart-test-123"
        }
        
        messages = await sip_message_handler.create_multipart_messages(multipart_data)
        
        assert len(messages) > 1
        assert all("MESSAGE" in msg for msg in messages)
        
        # Verify segmentation headers
        for i, msg in enumerate(messages):
            assert f"X-SMS-Part: {i+1}/{len(messages)}" in msg
            assert f"X-SMS-Reference: multipart-test-123" in msg


class TestSMSIntegration:
    """Integration tests for SMS system components."""
    
    @pytest.fixture
    async def sms_system(self):
        """Create integrated SMS system."""
        manager = SMSManager()
        await manager.initialize()
        
        processor = SMSProcessor()
        queue = SMSQueue()
        await queue.start()
        
        handler = SIPMessageHandler()
        
        system = {
            'manager': manager,
            'processor': processor,
            'queue': queue,
            'handler': handler
        }
        
        yield system
        
        # Cleanup
        await manager.cleanup()
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_end_to_end_sms_flow(self, sms_system):
        """Test complete SMS sending flow."""
        manager = sms_system['manager']
        queue = sms_system['queue']
        handler = sms_system['handler']
        
        # Mock the actual SIP sending
        with patch.object(handler, 'send_sip_message', return_value=True):
            # Send SMS through manager
            result = await manager.send_sms(
                from_number="+1234567890",
                to_number="+0987654321",
                message="End-to-end test message"
            )
        
        assert result.status == "sent"
        assert result.message == "End-to-end test message"
    
    @pytest.mark.asyncio
    async def test_incoming_sms_processing(self, sms_system):
        """Test incoming SMS message processing."""
        processor = sms_system['processor']
        
        incoming_sms = {
            "from_uri": "sip:+9876543210@external.com",
            "to_uri": "sip:+1234567890@our-domain.com",
            "body": "Incoming test message",
            "headers": {"Content-Type": "text/plain"}
        }
        
        # Mock webhook delivery
        with patch.object(processor, 'deliver_webhook', return_value=True):
            result = await processor.process_incoming_message(incoming_sms)
        
        assert result.direction == "inbound"
        assert result.from_number == "+9876543210"
        assert result.message == "Incoming test message"
    
    @pytest.mark.asyncio
    async def test_queue_integration(self, sms_system):
        """Test SMS queue integration with manager."""
        manager = sms_system['manager']
        queue = sms_system['queue']
        
        # Configure manager to use queue
        manager.enable_queuing(True)
        
        # Send multiple SMS messages
        messages = []
        for i in range(5):
            with patch.object(manager, '_send_sip_message', return_value=True):
                result = await manager.send_sms(
                    from_number="+1234567890",
                    to_number=f"+098765432{i}",
                    message=f"Queue test message {i}"
                )
                messages.append(result)
        
        # Verify all messages were processed
        assert len(messages) == 5
        assert all(msg.status == "sent" for msg in messages)


class TestSMSPerformance:
    """Performance tests for SMS functionality."""
    
    @pytest.mark.asyncio
    async def test_sms_throughput(self):
        """Test SMS sending throughput."""
        manager = SMSManager()
        await manager.initialize()
        
        try:
            # Mock SIP sending for performance test
            with patch.object(manager, '_send_sip_message', return_value=True):
                start_time = time.time()
                
                # Send 100 SMS messages
                tasks = []
                for i in range(100):
                    task = manager.send_sms(
                        from_number="+1234567890",
                        to_number=f"+0987654{i:03d}",
                        message=f"Performance test message {i}"
                    )
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks)
                
                end_time = time.time()
                duration = end_time - start_time
                throughput = len(results) / duration
                
                print(f"SMS Throughput: {throughput:.1f} messages/second")
                
                assert len(results) == 100
                assert all(result.status == "sent" for result in results)
                assert throughput > 10  # Should handle at least 10 SMS/sec
        
        finally:
            await manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_queue_performance(self):
        """Test SMS queue performance under load."""
        queue = SMSQueue(max_size=1000)
        await queue.start()
        
        try:
            # Enqueue many messages quickly
            start_time = time.time()
            
            for i in range(500):
                task = {
                    "message_id": f"perf-test-{i}",
                    "from_number": "+1234567890",
                    "to_number": f"+0987654{i:03d}",
                    "message": f"Performance test {i}",
                    "priority": "normal"
                }
                await queue.enqueue(task)
            
            enqueue_time = time.time() - start_time
            
            # Dequeue all messages
            start_time = time.time()
            dequeued_count = 0
            
            while queue.size() > 0:
                task = await queue.dequeue()
                if task:
                    dequeued_count += 1
            
            dequeue_time = time.time() - start_time
            
            print(f"Queue Performance:")
            print(f"  Enqueue: {500/enqueue_time:.1f} ops/sec")
            print(f"  Dequeue: {dequeued_count/dequeue_time:.1f} ops/sec")
            
            assert dequeued_count == 500
            assert enqueue_time < 5.0  # Should enqueue 500 messages in < 5 seconds
            assert dequeue_time < 5.0  # Should dequeue 500 messages in < 5 seconds
        
        finally:
            await queue.stop()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
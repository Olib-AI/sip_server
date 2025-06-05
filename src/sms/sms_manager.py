"""SMS Management System for SIP server."""
import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import re

from .sms_queue import SMSQueue, SMSQueuePriority
from .sms_processor import SMSProcessor

logger = logging.getLogger(__name__)


class SMSDirection(Enum):
    """SMS direction types."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SMSStatus(Enum):
    """SMS status types."""
    PENDING = "pending"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


class SMSEncoding(Enum):
    """SMS encoding types."""
    GSM7 = "gsm7"
    UCS2 = "ucs2"
    UTF8 = "utf8"


@dataclass
class SMSMessage:
    """SMS message data structure."""
    message_id: str
    from_number: str
    to_number: str
    message: str
    direction: SMSDirection
    status: SMSStatus
    created_at: datetime
    
    # Optional fields
    encoding: SMSEncoding = SMSEncoding.UTF8
    segments: int = 1
    priority: SMSQueuePriority = SMSQueuePriority.NORMAL
    
    # Delivery tracking
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # SIP specific
    sip_call_id: Optional[str] = None
    sip_headers: Dict[str, str] = field(default_factory=dict)
    
    # Metadata
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    webhook_url: Optional[str] = None
    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate SMS segments and set expiration."""
        self.segments = self._calculate_segments()
        if not self.expires_at:
            # Default expiration: 24 hours
            self.expires_at = self.created_at + timedelta(hours=24)
    
    def _calculate_segments(self) -> int:
        """Calculate number of SMS segments needed."""
        if self.encoding == SMSEncoding.GSM7:
            # GSM 7-bit encoding
            single_sms_limit = 160
            multi_sms_limit = 153  # Due to concatenation headers
        else:
            # UCS-2/UTF-8 encoding
            single_sms_limit = 70
            multi_sms_limit = 67
        
        message_length = len(self.message)
        
        if message_length <= single_sms_limit:
            return 1
        else:
            return (message_length - 1) // multi_sms_limit + 1
    
    def is_expired(self) -> bool:
        """Check if message has expired."""
        return datetime.utcnow() > self.expires_at
    
    def can_retry(self) -> bool:
        """Check if message can be retried."""
        return self.retry_count < self.max_retries and not self.is_expired()


class SMSStatistics:
    """SMS statistics tracking."""
    
    def __init__(self):
        self.total_messages = 0
        self.inbound_messages = 0
        self.outbound_messages = 0
        self.delivered_messages = 0
        self.failed_messages = 0
        self.start_time = time.time()
        
        # Message counts by status
        self.status_counts: Dict[SMSStatus, int] = {status: 0 for status in SMSStatus}
        
        # Error tracking
        self.error_counts: Dict[str, int] = {}
        
    def update_message_status(self, old_status: SMSStatus, new_status: SMSStatus):
        """Update statistics when message status changes."""
        if old_status != new_status:
            self.status_counts[old_status] -= 1
            self.status_counts[new_status] += 1
            
            if new_status == SMSStatus.DELIVERED:
                self.delivered_messages += 1
            elif new_status == SMSStatus.FAILED:
                self.failed_messages += 1
    
    def add_message(self, message: SMSMessage):
        """Add new message to statistics."""
        self.total_messages += 1
        self.status_counts[message.status] += 1
        
        if message.direction == SMSDirection.INBOUND:
            self.inbound_messages += 1
        else:
            self.outbound_messages += 1
    
    def add_error(self, error_type: str):
        """Track error occurrence."""
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        uptime = time.time() - self.start_time
        
        return {
            "uptime_seconds": int(uptime),
            "total_messages": self.total_messages,
            "inbound_messages": self.inbound_messages,
            "outbound_messages": self.outbound_messages,
            "delivered_messages": self.delivered_messages,
            "failed_messages": self.failed_messages,
            "delivery_rate": self.delivered_messages / max(self.total_messages, 1),
            "messages_per_hour": self.total_messages / max(uptime / 3600, 1),
            "status_breakdown": {status.value: count for status, count in self.status_counts.items()},
            "error_breakdown": dict(self.error_counts)
        }


class SMSManager:
    """Main SMS management system."""
    
    def __init__(self, kamailio_integration=None, ai_websocket_manager=None, database_session=None):
        self.kamailio_integration = kamailio_integration
        self.ai_websocket_manager = ai_websocket_manager
        self.database_session = database_session
        
        # Core components
        self.active_messages: Dict[str, SMSMessage] = {}
        self.sms_queue = SMSQueue()
        self.sms_processor = SMSProcessor(self, ai_websocket_manager)
        
        # Configuration
        self.max_concurrent_messages = 100
        self.default_encoding = SMSEncoding.UTF8
        self.delivery_timeout_hours = 24
        self.retry_interval_seconds = 300  # 5 minutes
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Statistics
        self.statistics = SMSStatistics()
        
        # Background tasks
        self._processing_task = None
        self._cleanup_task = None
        
        # Start background processing
        self.start_processing()
    
    def start_processing(self):
        """Start background SMS processing."""
        if not self._processing_task or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_sms_queue())
        
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_messages())
        
        logger.info("SMS processing started")
    
    async def stop_processing(self):
        """Stop background SMS processing."""
        tasks = []
        
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            tasks.append(self._processing_task)
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            tasks.append(self._cleanup_task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("SMS processing stopped")
    
    async def send_sms(self, from_number: str, to_number: str, message: str,
                      priority: SMSQueuePriority = SMSQueuePriority.NORMAL,
                      webhook_url: Optional[str] = None,
                      custom_data: Optional[Dict[str, Any]] = None) -> SMSMessage:
        """Send SMS message."""
        try:
            # Validate input
            self._validate_sms_input(from_number, to_number, message)
            
            # Create SMS message
            sms_message = SMSMessage(
                message_id=str(uuid.uuid4()),
                from_number=from_number,
                to_number=to_number,
                message=message,
                direction=SMSDirection.OUTBOUND,
                status=SMSStatus.PENDING,
                created_at=datetime.utcnow(),
                priority=priority,
                webhook_url=webhook_url,
                custom_data=custom_data or {}
            )
            
            # Store message
            self.active_messages[sms_message.message_id] = sms_message
            self.statistics.add_message(sms_message)
            
            # Queue for processing
            await self.sms_queue.enqueue(sms_message)
            
            # Update status
            await self._update_message_status(sms_message.message_id, SMSStatus.QUEUED)
            
            # Emit event
            await self._emit_event("sms_queued", sms_message)
            
            logger.info(f"SMS queued: {sms_message.message_id} from {from_number} to {to_number}")
            
            return sms_message
            
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            raise
    
    async def receive_sms(self, sip_data: Dict[str, Any]) -> SMSMessage:
        """Process incoming SMS from SIP MESSAGE."""
        try:
            # Extract SMS data from SIP MESSAGE
            from_number = self._extract_number_from_uri(sip_data.get("from_uri", ""))
            to_number = self._extract_number_from_uri(sip_data.get("to_uri", ""))
            message_body = sip_data.get("body", "")
            sip_call_id = sip_data.get("call_id", "")
            headers = sip_data.get("headers", {})
            
            # Create SMS message
            sms_message = SMSMessage(
                message_id=str(uuid.uuid4()),
                from_number=from_number,
                to_number=to_number,
                message=message_body,
                direction=SMSDirection.INBOUND,
                status=SMSStatus.DELIVERED,  # Inbound messages are already delivered
                created_at=datetime.utcnow(),
                delivered_at=datetime.utcnow(),
                sip_call_id=sip_call_id,
                sip_headers=headers
            )
            
            # Store message
            self.active_messages[sms_message.message_id] = sms_message
            self.statistics.add_message(sms_message)
            
            # Process through SMS processor (AI routing, etc.)
            await self.sms_processor.process_inbound_sms(sms_message)
            
            # Store in database
            await self._store_message_in_database(sms_message)
            
            # Emit event
            await self._emit_event("sms_received", sms_message)
            
            logger.info(f"SMS received: {sms_message.message_id} from {from_number} to {to_number}")
            
            return sms_message
            
        except Exception as e:
            logger.error(f"Error processing incoming SMS: {e}")
            raise
    
    async def get_message_status(self, message_id: str) -> Optional[SMSMessage]:
        """Get SMS message status."""
        return self.active_messages.get(message_id)
    
    async def get_message_history(self, number: Optional[str] = None, 
                                 limit: int = 100, offset: int = 0) -> List[SMSMessage]:
        """Get SMS message history."""
        try:
            # This would query the database for message history
            # For now, return from active messages
            messages = list(self.active_messages.values())
            
            if number:
                messages = [
                    msg for msg in messages 
                    if msg.from_number == number or msg.to_number == number
                ]
            
            # Sort by creation time (newest first)
            messages.sort(key=lambda m: m.created_at, reverse=True)
            
            # Apply pagination
            return messages[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Error getting message history: {e}")
            return []
    
    async def retry_failed_message(self, message_id: str) -> bool:
        """Retry failed SMS message."""
        try:
            message = self.active_messages.get(message_id)
            if not message:
                logger.warning(f"Message {message_id} not found for retry")
                return False
            
            if not message.can_retry():
                logger.warning(f"Message {message_id} cannot be retried")
                return False
            
            # Reset status and re-queue
            message.retry_count += 1
            await self._update_message_status(message_id, SMSStatus.QUEUED)
            await self.sms_queue.enqueue(message)
            
            logger.info(f"Retrying SMS message {message_id} (attempt {message.retry_count})")
            return True
            
        except Exception as e:
            logger.error(f"Error retrying message {message_id}: {e}")
            return False
    
    async def cancel_message(self, message_id: str) -> bool:
        """Cancel pending SMS message."""
        try:
            message = self.active_messages.get(message_id)
            if not message:
                return False
            
            if message.status in [SMSStatus.SENT, SMSStatus.DELIVERED]:
                logger.warning(f"Cannot cancel already sent message {message_id}")
                return False
            
            await self._update_message_status(message_id, SMSStatus.FAILED)
            message.error_message = "Cancelled by user"
            
            # Remove from queue if still queued
            await self.sms_queue.remove(message_id)
            
            await self._emit_event("sms_cancelled", message)
            
            logger.info(f"Cancelled SMS message {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling message {message_id}: {e}")
            return False
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """Add SMS event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def remove_event_handler(self, event_type: str, handler: Callable):
        """Remove SMS event handler."""
        if event_type in self.event_handlers and handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
    
    async def _process_sms_queue(self):
        """Background task to process SMS queue."""
        logger.info("Started SMS queue processing")
        
        try:
            while True:
                try:
                    # Check if we're under the concurrent limit
                    sending_count = len([
                        msg for msg in self.active_messages.values()
                        if msg.status == SMSStatus.SENDING
                    ])
                    
                    if sending_count >= self.max_concurrent_messages:
                        await asyncio.sleep(1)
                        continue
                    
                    # Get next message from queue
                    message = await self.sms_queue.dequeue()
                    
                    if message:
                        await self._send_message_via_sip(message)
                    else:
                        # No messages in queue, wait a bit
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Error in SMS queue processing: {e}")
                    await asyncio.sleep(5)  # Wait before retrying
                    
        except asyncio.CancelledError:
            logger.info("SMS queue processing cancelled")
        except Exception as e:
            logger.error(f"Fatal error in SMS queue processing: {e}")
    
    async def _send_message_via_sip(self, message: SMSMessage):
        """Send SMS message via SIP MESSAGE method."""
        try:
            # Update status
            await self._update_message_status(message.message_id, SMSStatus.SENDING)
            
            if not self.kamailio_integration:
                raise Exception("Kamailio integration not available")
            
            # Prepare SIP MESSAGE data
            sip_data = {
                "method": "MESSAGE",
                "from_uri": f"sip:{message.from_number}@{self._get_domain()}",
                "to_uri": f"sip:{message.to_number}@{self._get_domain()}",
                "body": message.message,
                "content_type": "text/plain; charset=utf-8",
                "headers": {
                    "X-SMS-ID": message.message_id,
                    "X-SMS-Segments": str(message.segments),
                    **message.sip_headers
                }
            }
            
            # Send via Kamailio
            result = await self.kamailio_integration.send_sip_message(sip_data)
            
            if result.get("success"):
                # Message sent successfully
                message.sent_at = datetime.utcnow()
                await self._update_message_status(message.message_id, SMSStatus.SENT)
                
                # Start delivery confirmation timer
                asyncio.create_task(self._handle_delivery_timeout(message.message_id))
                
                await self._emit_event("sms_sent", message)
                
                logger.info(f"SMS sent successfully: {message.message_id}")
                
            else:
                # Send failed
                error_msg = result.get("error", "Unknown error")
                await self._handle_send_failure(message, error_msg)
                
        except Exception as e:
            logger.error(f"Error sending SMS {message.message_id}: {e}")
            await self._handle_send_failure(message, str(e))
    
    async def _handle_send_failure(self, message: SMSMessage, error: str):
        """Handle SMS send failure."""
        message.error_message = error
        self.statistics.add_error("send_failure")
        
        # Check if we should retry
        if message.can_retry():
            logger.info(f"Will retry SMS {message.message_id} in {self.retry_interval_seconds} seconds")
            
            # Schedule retry
            asyncio.create_task(self._schedule_retry(message))
        else:
            # Mark as failed
            await self._update_message_status(message.message_id, SMSStatus.FAILED)
            await self._emit_event("sms_failed", message)
            
            logger.error(f"SMS failed permanently: {message.message_id} - {error}")
    
    async def _schedule_retry(self, message: SMSMessage):
        """Schedule SMS retry."""
        try:
            await asyncio.sleep(self.retry_interval_seconds)
            
            # Check if message still exists and can be retried
            if (message.message_id in self.active_messages and 
                message.can_retry()):
                
                message.retry_count += 1
                await self._update_message_status(message.message_id, SMSStatus.QUEUED)
                await self.sms_queue.enqueue(message)
                
        except Exception as e:
            logger.error(f"Error scheduling retry for {message.message_id}: {e}")
    
    async def _handle_delivery_timeout(self, message_id: str):
        """Handle delivery confirmation timeout."""
        try:
            # Wait for delivery confirmation timeout (e.g., 30 minutes)
            await asyncio.sleep(1800)
            
            message = self.active_messages.get(message_id)
            if message and message.status == SMSStatus.SENT:
                # No delivery confirmation received, assume delivered
                await self._update_message_status(message_id, SMSStatus.DELIVERED)
                message.delivered_at = datetime.utcnow()
                
                await self._emit_event("sms_delivered", message)
                
        except Exception as e:
            logger.error(f"Error in delivery timeout handler: {e}")
    
    async def _update_message_status(self, message_id: str, new_status: SMSStatus):
        """Update message status."""
        message = self.active_messages.get(message_id)
        if not message:
            return
        
        old_status = message.status
        message.status = new_status
        
        # Update statistics
        self.statistics.update_message_status(old_status, new_status)
        
        # Update database
        await self._store_message_in_database(message)
        
        logger.debug(f"SMS {message_id} status: {old_status.value} -> {new_status.value}")
    
    async def _cleanup_expired_messages(self):
        """Background task to cleanup expired messages."""
        logger.info("Started SMS cleanup task")
        
        try:
            while True:
                try:
                    current_time = datetime.utcnow()
                    expired_messages = []
                    
                    for message_id, message in self.active_messages.items():
                        if message.is_expired() or current_time > message.created_at + timedelta(days=7):
                            expired_messages.append(message_id)
                    
                    for message_id in expired_messages:
                        message = self.active_messages.pop(message_id, None)
                        if message and message.status not in [SMSStatus.DELIVERED, SMSStatus.FAILED]:
                            await self._update_message_status(message_id, SMSStatus.EXPIRED)
                            await self._emit_event("sms_expired", message)
                        
                        logger.debug(f"Cleaned up expired SMS: {message_id}")
                    
                    # Run cleanup every hour
                    await asyncio.sleep(3600)
                    
                except Exception as e:
                    logger.error(f"Error in SMS cleanup: {e}")
                    await asyncio.sleep(300)  # Wait 5 minutes before retry
                    
        except asyncio.CancelledError:
            logger.info("SMS cleanup task cancelled")
    
    async def _store_message_in_database(self, message: SMSMessage):
        """Store SMS message in database."""
        try:
            if not self.database_session:
                return
            
            # This would store the message in the database
            # Implementation depends on your database setup
            logger.debug(f"Stored SMS {message.message_id} in database")
            
        except Exception as e:
            logger.error(f"Error storing SMS in database: {e}")
    
    async def _emit_event(self, event_type: str, *args, **kwargs):
        """Emit SMS event to handlers."""
        handlers = self.event_handlers.get(event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in SMS event handler for {event_type}: {e}")
    
    def _validate_sms_input(self, from_number: str, to_number: str, message: str):
        """Validate SMS input parameters."""
        if not from_number or not to_number:
            raise ValueError("From and to numbers are required")
        
        if not message or len(message.strip()) == 0:
            raise ValueError("Message content is required")
        
        if len(message) > 1600:
            raise ValueError("Message too long (max 1600 characters)")
        
        # Basic phone number validation
        phone_pattern = r'^\+?[\d\s\-\(\)]{10,}$'
        if not re.match(phone_pattern, from_number):
            raise ValueError(f"Invalid from number: {from_number}")
        
        if not re.match(phone_pattern, to_number):
            raise ValueError(f"Invalid to number: {to_number}")
    
    def _extract_number_from_uri(self, uri: str) -> str:
        """Extract phone number from SIP URI."""
        if not uri:
            return "unknown"
        
        # Remove sip: prefix
        if uri.startswith("sip:"):
            uri = uri[4:]
        
        # Extract user part before @
        if "@" in uri:
            return uri.split("@")[0]
        
        return uri
    
    def _get_domain(self) -> str:
        """Get SIP domain."""
        return "sip.olib.local"  # This should be configurable
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get SMS statistics."""
        stats = self.statistics.get_stats()
        stats.update({
            "active_messages": len(self.active_messages),
            "queue_size": self.sms_queue.size(),
            "queue_stats": self.sms_queue.get_statistics()
        })
        return stats
    
    async def cleanup(self):
        """Cleanup SMS manager resources."""
        try:
            logger.info("Cleaning up SMS manager...")
            
            # Stop background tasks
            await self.stop_processing()
            
            # Clear active messages
            self.active_messages.clear()
            
            # Cleanup processor
            await self.sms_processor.cleanup()
            
            logger.info("SMS manager cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during SMS manager cleanup: {e}")
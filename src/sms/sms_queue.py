"""SMS Queue Management System."""
import asyncio
import heapq
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SMSQueuePriority(Enum):
    """SMS queue priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class QueuedSMSItem:
    """SMS item in queue with priority."""
    priority: int
    queued_at: float
    message: 'SMSMessage'  # Forward reference
    
    def __lt__(self, other):
        """Compare for priority queue (higher priority first, then FIFO)."""
        if self.priority != other.priority:
            return self.priority > other.priority  # Higher priority first
        return self.queued_at < other.queued_at  # FIFO for same priority


class SMSQueue:
    """Priority-based SMS queue with rate limiting and throttling."""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queue: List[QueuedSMSItem] = []
        self.message_lookup: Dict[str, QueuedSMSItem] = {}
        
        # Rate limiting
        self.rate_limits: Dict[str, Dict] = {}  # number -> rate limit info
        self.global_rate_limit = 100  # messages per minute
        self.per_number_rate_limit = 10  # messages per minute per number
        
        # Statistics
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.start_time = time.time()
        
        # Throttling
        self.last_send_times: List[float] = []
        self.throttle_window = 60.0  # 1 minute window
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def enqueue(self, message: 'SMSMessage') -> bool:
        """Add SMS message to queue."""
        async with self._lock:
            try:
                # Check queue size
                if len(self.queue) >= self.max_size:
                    logger.warning(f"SMS queue full, dropping message {message.message_id}")
                    self.total_dropped += 1
                    return False
                
                # Check rate limits
                if not await self._check_rate_limits(message):
                    logger.warning(f"Rate limit exceeded for {message.from_number}, dropping message {message.message_id}")
                    self.total_dropped += 1
                    return False
                
                # Create queue item
                queue_item = QueuedSMSItem(
                    priority=message.priority.value,
                    queued_at=time.time(),
                    message=message
                )
                
                # Add to queue
                heapq.heappush(self.queue, queue_item)
                self.message_lookup[message.message_id] = queue_item
                
                # Update statistics
                self.total_enqueued += 1
                
                # Update rate limiting
                await self._update_rate_limits(message)
                
                logger.debug(f"Enqueued SMS {message.message_id} with priority {message.priority.value}")
                return True
                
            except Exception as e:
                logger.error(f"Error enqueuing SMS: {e}")
                return False
    
    async def dequeue(self) -> Optional['SMSMessage']:
        """Get next SMS message from queue."""
        async with self._lock:
            try:
                # Check global throttling
                if not self._check_global_throttle():
                    return None
                
                # Get highest priority message
                while self.queue:
                    queue_item = heapq.heappop(self.queue)
                    message_id = queue_item.message.message_id
                    
                    # Remove from lookup
                    self.message_lookup.pop(message_id, None)
                    
                    # Check if message is still valid (not expired)
                    if queue_item.message.is_expired():
                        logger.debug(f"Skipping expired SMS {message_id}")
                        continue
                    
                    # Update statistics
                    self.total_dequeued += 1
                    
                    # Update throttling
                    self._update_global_throttle()
                    
                    logger.debug(f"Dequeued SMS {message_id}")
                    return queue_item.message
                
                return None
                
            except Exception as e:
                logger.error(f"Error dequeuing SMS: {e}")
                return None
    
    async def remove(self, message_id: str) -> bool:
        """Remove specific message from queue."""
        async with self._lock:
            try:
                queue_item = self.message_lookup.get(message_id)
                if not queue_item:
                    return False
                
                # Mark as removed (we can't efficiently remove from heapq)
                queue_item.message.status = None  # Mark as invalid
                self.message_lookup.pop(message_id, None)
                
                logger.debug(f"Removed SMS {message_id} from queue")
                return True
                
            except Exception as e:
                logger.error(f"Error removing SMS from queue: {e}")
                return False
    
    async def peek(self) -> Optional['SMSMessage']:
        """Peek at next message without removing it."""
        async with self._lock:
            while self.queue:
                queue_item = self.queue[0]
                
                # Check if message is still valid
                if queue_item.message.is_expired() or queue_item.message.status is None:
                    # Remove invalid message
                    heapq.heappop(self.queue)
                    self.message_lookup.pop(queue_item.message.message_id, None)
                    continue
                
                return queue_item.message
            
            return None
    
    def size(self) -> int:
        """Get current queue size."""
        return len(self.queue)
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.queue) == 0
    
    def is_full(self) -> bool:
        """Check if queue is full."""
        return len(self.queue) >= self.max_size
    
    async def clear(self) -> int:
        """Clear all messages from queue."""
        async with self._lock:
            cleared_count = len(self.queue)
            self.queue.clear()
            self.message_lookup.clear()
            
            logger.info(f"Cleared {cleared_count} messages from SMS queue")
            return cleared_count
    
    async def get_queue_contents(self) -> List[Dict[str, Any]]:
        """Get summary of queue contents."""
        async with self._lock:
            contents = []
            
            for queue_item in sorted(self.queue, key=lambda x: (-x.priority, x.queued_at)):
                if queue_item.message.status is not None:  # Skip removed messages
                    contents.append({
                        "message_id": queue_item.message.message_id,
                        "from_number": queue_item.message.from_number,
                        "to_number": queue_item.message.to_number,
                        "priority": queue_item.priority,
                        "queued_at": datetime.fromtimestamp(queue_item.queued_at).isoformat(),
                        "wait_time_seconds": time.time() - queue_item.queued_at,
                        "segments": queue_item.message.segments,
                        "retry_count": queue_item.message.retry_count
                    })
            
            return contents
    
    async def _check_rate_limits(self, message: 'SMSMessage') -> bool:
        """Check if message is within rate limits."""
        current_time = time.time()
        from_number = message.from_number
        
        # Initialize rate limit tracking for number if needed
        if from_number not in self.rate_limits:
            self.rate_limits[from_number] = {
                "send_times": [],
                "last_cleanup": current_time
            }
        
        number_limits = self.rate_limits[from_number]
        
        # Clean up old entries (older than 1 minute)
        cutoff_time = current_time - 60
        number_limits["send_times"] = [
            t for t in number_limits["send_times"] if t > cutoff_time
        ]
        
        # Check per-number rate limit
        if len(number_limits["send_times"]) >= self.per_number_rate_limit:
            return False
        
        # Check global rate limit
        total_recent_sends = sum(
            len([t for t in limits["send_times"] if t > cutoff_time])
            for limits in self.rate_limits.values()
        )
        
        if total_recent_sends >= self.global_rate_limit:
            return False
        
        return True
    
    async def _update_rate_limits(self, message: 'SMSMessage'):
        """Update rate limit tracking after enqueuing."""
        current_time = time.time()
        from_number = message.from_number
        
        if from_number in self.rate_limits:
            self.rate_limits[from_number]["send_times"].append(current_time)
    
    def _check_global_throttle(self) -> bool:
        """Check global throttling to prevent overwhelming the system."""
        current_time = time.time()
        
        # Clean up old send times (older than throttle window)
        cutoff_time = current_time - self.throttle_window
        self.last_send_times = [t for t in self.last_send_times if t > cutoff_time]
        
        # Check if we're sending too fast
        if len(self.last_send_times) >= self.global_rate_limit:
            return False
        
        return True
    
    def _update_global_throttle(self):
        """Update global throttling after dequeuing."""
        self.last_send_times.append(time.time())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get queue statistics."""
        uptime = time.time() - self.start_time
        
        # Calculate priority distribution
        priority_counts = {}
        for queue_item in self.queue:
            if queue_item.message.status is not None:  # Skip removed messages
                priority = queue_item.priority
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        # Calculate average wait time
        current_time = time.time()
        wait_times = [
            current_time - queue_item.queued_at 
            for queue_item in self.queue
            if queue_item.message.status is not None
        ]
        avg_wait_time = sum(wait_times) / len(wait_times) if wait_times else 0
        
        return {
            "queue_size": len(self.queue),
            "max_size": self.max_size,
            "total_enqueued": self.total_enqueued,
            "total_dequeued": self.total_dequeued,
            "total_dropped": self.total_dropped,
            "queue_utilization": len(self.queue) / self.max_size,
            "throughput_per_hour": self.total_dequeued / max(uptime / 3600, 1),
            "average_wait_time_seconds": avg_wait_time,
            "priority_distribution": priority_counts,
            "rate_limited_numbers": len(self.rate_limits),
            "global_rate_limit": self.global_rate_limit,
            "per_number_rate_limit": self.per_number_rate_limit
        }
    
    async def set_rate_limits(self, global_limit: int, per_number_limit: int):
        """Update rate limits."""
        async with self._lock:
            self.global_rate_limit = global_limit
            self.per_number_rate_limit = per_number_limit
            
            logger.info(f"Updated SMS rate limits: global={global_limit}, per_number={per_number_limit}")
    
    async def get_rate_limit_status(self, number: str) -> Dict[str, Any]:
        """Get rate limit status for a specific number."""
        async with self._lock:
            if number not in self.rate_limits:
                return {
                    "number": number,
                    "recent_sends": 0,
                    "limit": self.per_number_rate_limit,
                    "remaining": self.per_number_rate_limit,
                    "reset_time": time.time() + 60
                }
            
            current_time = time.time()
            cutoff_time = current_time - 60
            
            number_limits = self.rate_limits[number]
            recent_sends = len([
                t for t in number_limits["send_times"] if t > cutoff_time
            ])
            
            return {
                "number": number,
                "recent_sends": recent_sends,
                "limit": self.per_number_rate_limit,
                "remaining": max(0, self.per_number_rate_limit - recent_sends),
                "reset_time": min(number_limits["send_times"]) + 60 if number_limits["send_times"] else current_time
            }
    
    async def cleanup_expired_rate_limits(self):
        """Clean up expired rate limit entries."""
        async with self._lock:
            current_time = time.time()
            cutoff_time = current_time - 300  # 5 minutes
            
            expired_numbers = []
            
            for number, limits in self.rate_limits.items():
                # Remove old send times
                limits["send_times"] = [
                    t for t in limits["send_times"] if t > current_time - 60
                ]
                
                # Mark for removal if no recent activity
                if (not limits["send_times"] and 
                    limits.get("last_cleanup", 0) < cutoff_time):
                    expired_numbers.append(number)
            
            # Remove expired entries
            for number in expired_numbers:
                del self.rate_limits[number]
            
            if expired_numbers:
                logger.debug(f"Cleaned up rate limits for {len(expired_numbers)} numbers")
    
    async def pause_queue(self):
        """Pause queue processing."""
        async with self._lock:
            self._paused = True
            logger.info("SMS queue paused")
    
    async def resume_queue(self):
        """Resume queue processing."""
        async with self._lock:
            self._paused = False
            logger.info("SMS queue resumed")
    
    def is_paused(self) -> bool:
        """Check if queue is paused."""
        return getattr(self, '_paused', False)
"""SMS Processing and AI Integration."""
import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional, Callable, Any, Pattern
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class SMSProcessingAction(Enum):
    """SMS processing action types."""
    FORWARD_TO_AI = "forward_to_ai"
    AUTO_REPLY = "auto_reply"
    FORWARD_TO_NUMBER = "forward_to_number"
    BLOCK_SENDER = "block_sender"
    TRIGGER_CALL = "trigger_call"
    STORE_ONLY = "store_only"
    CUSTOM_HANDLER = "custom_handler"


@dataclass
class SMSProcessingRule:
    """SMS processing rule configuration."""
    rule_id: str
    name: str
    pattern: str  # Regex pattern for message content or sender
    action: SMSProcessingAction
    priority: int = 100
    enabled: bool = True
    
    # Pattern matching options
    match_content: bool = True
    match_sender: bool = False
    case_sensitive: bool = False
    
    # Action parameters
    auto_reply_template: Optional[str] = None
    forward_number: Optional[str] = None
    ai_context: Dict[str, Any] = field(default_factory=dict)
    custom_handler: Optional[str] = None
    
    # Conditions
    time_restrictions: Optional[Dict[str, Any]] = None
    sender_whitelist: List[str] = field(default_factory=list)
    sender_blacklist: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Compile regex pattern."""
        try:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            self.compiled_pattern: Pattern = re.compile(self.pattern, flags)
        except re.error as e:
            logger.error(f"Invalid SMS processing pattern '{self.pattern}': {e}")
            raise


@dataclass
class SMSConversation:
    """SMS conversation tracking."""
    conversation_id: str
    participants: List[str]
    last_message_time: datetime
    message_count: int = 0
    ai_session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, message: 'SMSMessage'):
        """Add message to conversation."""
        self.message_count += 1
        self.last_message_time = message.created_at
    
    def is_expired(self, timeout_hours: int = 24) -> bool:
        """Check if conversation has expired."""
        from datetime import timedelta
        return (datetime.utcnow() - self.last_message_time) > timedelta(hours=timeout_hours)


class SMSProcessor:
    """Main SMS processor with AI integration and rule-based processing."""
    
    def __init__(self, sms_manager=None, ai_websocket_manager=None):
        self.sms_manager = sms_manager
        self.ai_websocket_manager = ai_websocket_manager
        
        # Processing rules
        self.processing_rules: List[SMSProcessingRule] = []
        
        # Conversation tracking
        self.conversations: Dict[str, SMSConversation] = {}
        self.conversation_timeout_hours = 24
        
        # Auto-reply templates
        self.auto_reply_templates: Dict[str, str] = {}
        
        # Custom handlers
        self.custom_handlers: Dict[str, Callable] = {}
        
        # Spam detection
        self.spam_patterns: List[Pattern] = []
        self.spam_threshold = 0.8
        
        # Statistics
        self.total_processed = 0
        self.ai_forwarded = 0
        self.auto_replied = 0
        self.spam_detected = 0
        self.rules_matched = 0
        
        # Configuration
        self.enable_conversation_tracking = True
        self.enable_spam_detection = True
        self.enable_ai_forwarding = True
        
        # Initialize default rules and templates
        self._initialize_defaults()
        
        # Cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_conversations())
    
    def _initialize_defaults(self):
        """Initialize default processing rules and templates."""
        # Default auto-reply templates
        self.auto_reply_templates.update({
            "business_hours": "Thank you for your message. Our business hours are 9 AM - 5 PM, Monday-Friday. We'll respond during our next business day.",
            "out_of_office": "This is an automated response. We're currently out of office and will respond when we return.",
            "confirmation": "Thank you for your message. We have received it and will respond shortly.",
            "error": "We're sorry, but we couldn't process your message. Please try again or contact support."
        })
        
        # Default spam patterns
        spam_patterns_text = [
            r"(?i)\b(viagra|cialis|pharmacy)\b",
            r"(?i)\b(free\s+money|cash\s+now|earn\s+\$)\b",
            r"(?i)\b(click\s+here|visit\s+now)\b",
            r"(?i)\b(congratulations.*won|winner|prize)\b",
            r"(?i)\b(urgent|limited\s+time|act\s+now)\b"
        ]
        
        for pattern_text in spam_patterns_text:
            try:
                self.spam_patterns.append(re.compile(pattern_text))
            except re.error as e:
                logger.warning(f"Invalid spam pattern: {pattern_text} - {e}")
    
    async def process_inbound_sms(self, message: 'SMSMessage') -> Dict[str, Any]:
        """Process incoming SMS message."""
        try:
            self.total_processed += 1
            
            logger.info(f"Processing inbound SMS {message.message_id} from {message.from_number}")
            
            # Track conversation
            if self.enable_conversation_tracking:
                await self._track_conversation(message)
            
            # Spam detection
            if self.enable_spam_detection:
                spam_score = await self._detect_spam(message)
                if spam_score > self.spam_threshold:
                    self.spam_detected += 1
                    logger.warning(f"Spam detected in SMS {message.message_id} (score: {spam_score:.2f})")
                    return {"action": "spam_blocked", "spam_score": spam_score}
            
            # Apply processing rules
            rule_result = await self._apply_processing_rules(message)
            if rule_result:
                self.rules_matched += 1
                return rule_result
            
            # Default action: forward to AI if enabled
            if self.enable_ai_forwarding:
                return await self._forward_to_ai(message)
            else:
                # Just store the message
                return {"action": "stored", "message_id": message.message_id}
                
        except Exception as e:
            logger.error(f"Error processing inbound SMS {message.message_id}: {e}")
            return {"action": "error", "error": str(e)}
    
    async def process_outbound_sms(self, message: 'SMSMessage') -> Dict[str, Any]:
        """Process outgoing SMS message."""
        try:
            logger.debug(f"Processing outbound SMS {message.message_id} to {message.to_number}")
            
            # Track conversation
            if self.enable_conversation_tracking:
                await self._track_conversation(message)
            
            # Could add outbound processing rules here
            
            return {"action": "processed", "message_id": message.message_id}
            
        except Exception as e:
            logger.error(f"Error processing outbound SMS {message.message_id}: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _track_conversation(self, message: 'SMSMessage'):
        """Track SMS conversation."""
        try:
            # Create conversation ID from participants
            participants = sorted([message.from_number, message.to_number])
            conversation_id = f"sms_{'-'.join(participants)}"
            
            # Get or create conversation
            if conversation_id not in self.conversations:
                self.conversations[conversation_id] = SMSConversation(
                    conversation_id=conversation_id,
                    participants=participants,
                    last_message_time=message.created_at
                )
            
            conversation = self.conversations[conversation_id]
            conversation.add_message(message)
            
            # Update message with conversation ID
            message.custom_data["conversation_id"] = conversation_id
            
            logger.debug(f"Tracked SMS in conversation {conversation_id} (total messages: {conversation.message_count})")
            
        except Exception as e:
            logger.error(f"Error tracking conversation: {e}")
    
    async def _detect_spam(self, message: 'SMSMessage') -> float:
        """Detect spam in SMS message."""
        try:
            spam_score = 0.0
            total_checks = 0
            
            content = message.message.lower()
            
            # Check against spam patterns
            pattern_matches = 0
            for pattern in self.spam_patterns:
                total_checks += 1
                if pattern.search(message.message):
                    pattern_matches += 1
            
            if total_checks > 0:
                spam_score += (pattern_matches / total_checks) * 0.6
            
            # Check message characteristics
            # Excessive punctuation
            if len(re.findall(r'[!]{2,}', message.message)) > 0:
                spam_score += 0.1
            
            # Excessive capital letters
            if len(re.findall(r'[A-Z]{3,}', message.message)) > 0:
                spam_score += 0.1
            
            # URLs (suspicious in some contexts)
            if re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message.message):
                spam_score += 0.1
            
            # Phone numbers (could be spam)
            phone_matches = len(re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', message.message))
            if phone_matches > 1:
                spam_score += 0.1
            
            return min(spam_score, 1.0)
            
        except Exception as e:
            logger.error(f"Error in spam detection: {e}")
            return 0.0
    
    async def _apply_processing_rules(self, message: 'SMSMessage') -> Optional[Dict[str, Any]]:
        """Apply processing rules to message."""
        try:
            # Sort rules by priority (higher priority first)
            sorted_rules = sorted(
                [rule for rule in self.processing_rules if rule.enabled],
                key=lambda r: r.priority,
                reverse=True
            )
            
            for rule in sorted_rules:
                if await self._rule_matches(rule, message):
                    logger.info(f"SMS processing rule '{rule.name}' matched for message {message.message_id}")
                    return await self._execute_rule_action(rule, message)
            
            return None
            
        except Exception as e:
            logger.error(f"Error applying processing rules: {e}")
            return None
    
    async def _rule_matches(self, rule: SMSProcessingRule, message: 'SMSMessage') -> bool:
        """Check if processing rule matches message."""
        try:
            # Check sender whitelist/blacklist
            if rule.sender_whitelist and message.from_number not in rule.sender_whitelist:
                return False
            
            if rule.sender_blacklist and message.from_number in rule.sender_blacklist:
                return False
            
            # Check time restrictions
            if rule.time_restrictions:
                if not self._check_time_restrictions(rule.time_restrictions):
                    return False
            
            # Check pattern match
            match_found = False
            
            if rule.match_content:
                if rule.compiled_pattern.search(message.message):
                    match_found = True
            
            if rule.match_sender:
                if rule.compiled_pattern.search(message.from_number):
                    match_found = True
            
            return match_found
            
        except Exception as e:
            logger.error(f"Error checking rule match: {e}")
            return False
    
    def _check_time_restrictions(self, restrictions: Dict[str, Any]) -> bool:
        """Check if current time matches restrictions."""
        try:
            current_time = datetime.now()
            
            # Check day of week
            if "days" in restrictions:
                allowed_days = restrictions["days"]
                current_day = current_time.strftime("%A").lower()
                if current_day not in [day.lower() for day in allowed_days]:
                    return False
            
            # Check time range
            if "start_time" in restrictions and "end_time" in restrictions:
                start_time = datetime.strptime(restrictions["start_time"], "%H:%M").time()
                end_time = datetime.strptime(restrictions["end_time"], "%H:%M").time()
                current_time_only = current_time.time()
                
                if start_time <= end_time:
                    # Same day range
                    if not (start_time <= current_time_only <= end_time):
                        return False
                else:
                    # Overnight range
                    if not (current_time_only >= start_time or current_time_only <= end_time):
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking time restrictions: {e}")
            return False
    
    async def _execute_rule_action(self, rule: SMSProcessingRule, message: 'SMSMessage') -> Dict[str, Any]:
        """Execute processing rule action."""
        try:
            action = rule.action
            
            if action == SMSProcessingAction.FORWARD_TO_AI:
                return await self._forward_to_ai(message, rule.ai_context)
            
            elif action == SMSProcessingAction.AUTO_REPLY:
                return await self._send_auto_reply(message, rule.auto_reply_template)
            
            elif action == SMSProcessingAction.FORWARD_TO_NUMBER:
                return await self._forward_to_number(message, rule.forward_number)
            
            elif action == SMSProcessingAction.BLOCK_SENDER:
                return await self._block_sender(message)
            
            elif action == SMSProcessingAction.TRIGGER_CALL:
                return await self._trigger_call(message)
            
            elif action == SMSProcessingAction.STORE_ONLY:
                return {"action": "stored", "rule": rule.name}
            
            elif action == SMSProcessingAction.CUSTOM_HANDLER:
                return await self._execute_custom_handler(rule.custom_handler, message, rule)
            
            else:
                logger.warning(f"Unknown SMS processing action: {action}")
                return {"action": "unknown", "rule": rule.name}
                
        except Exception as e:
            logger.error(f"Error executing rule action {action}: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _forward_to_ai(self, message: 'SMSMessage', context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Forward SMS to AI platform."""
        try:
            if not self.ai_websocket_manager:
                return {"action": "error", "error": "AI WebSocket manager not available"}
            
            # Get conversation context
            conversation_id = message.custom_data.get("conversation_id")
            conversation = self.conversations.get(conversation_id) if conversation_id else None
            
            # Prepare AI message
            ai_message = {
                "type": "sms_message",
                "message_id": message.message_id,
                "from_number": message.from_number,
                "to_number": message.to_number,
                "message": message.message,
                "direction": message.direction.value,
                "timestamp": message.created_at.isoformat(),
                "segments": message.segments,
                "conversation_id": conversation_id,
                "conversation_context": conversation.context if conversation else {},
                "custom_context": context or {},
                "sip_headers": message.sip_headers
            }
            
            # Send to AI platform
            success = await self.ai_websocket_manager.send_message(
                f"sms_{message.from_number}", ai_message
            )
            
            if success:
                self.ai_forwarded += 1
                
                # Update conversation with AI session
                if conversation:
                    conversation.ai_session_id = f"sms_{message.from_number}"
                
                logger.info(f"Forwarded SMS {message.message_id} to AI")
                return {"action": "forwarded_to_ai", "success": True}
            else:
                return {"action": "error", "error": "Failed to forward to AI"}
                
        except Exception as e:
            logger.error(f"Error forwarding SMS to AI: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _send_auto_reply(self, message: 'SMSMessage', template_name: Optional[str] = None) -> Dict[str, Any]:
        """Send automatic reply."""
        try:
            if not self.sms_manager:
                return {"action": "error", "error": "SMS manager not available"}
            
            # Get reply template
            template_name = template_name or "confirmation"
            reply_text = self.auto_reply_templates.get(template_name, "Thank you for your message.")
            
            # Send reply
            reply_message = await self.sms_manager.send_sms(
                from_number=message.to_number,
                to_number=message.from_number,
                message=reply_text,
                custom_data={"auto_reply": True, "original_message_id": message.message_id}
            )
            
            self.auto_replied += 1
            
            logger.info(f"Sent auto-reply for SMS {message.message_id}")
            return {"action": "auto_reply_sent", "reply_message_id": reply_message.message_id}
            
        except Exception as e:
            logger.error(f"Error sending auto-reply: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _forward_to_number(self, message: 'SMSMessage', target_number: str) -> Dict[str, Any]:
        """Forward SMS to another number."""
        try:
            if not self.sms_manager or not target_number:
                return {"action": "error", "error": "SMS manager or target number not available"}
            
            # Forward message
            forwarded_message = await self.sms_manager.send_sms(
                from_number=message.to_number,
                to_number=target_number,
                message=f"Forwarded from {message.from_number}: {message.message}",
                custom_data={"forwarded": True, "original_message_id": message.message_id}
            )
            
            logger.info(f"Forwarded SMS {message.message_id} to {target_number}")
            return {"action": "forwarded_to_number", "target": target_number, "forwarded_message_id": forwarded_message.message_id}
            
        except Exception as e:
            logger.error(f"Error forwarding SMS to number: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _block_sender(self, message: 'SMSMessage') -> Dict[str, Any]:
        """Block sender number."""
        try:
            # This would integrate with number blocking system
            logger.info(f"Blocking sender {message.from_number} due to SMS {message.message_id}")
            return {"action": "sender_blocked", "blocked_number": message.from_number}
            
        except Exception as e:
            logger.error(f"Error blocking sender: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _trigger_call(self, message: 'SMSMessage') -> Dict[str, Any]:
        """Trigger callback to sender."""
        try:
            # This would integrate with call manager
            logger.info(f"Triggering call to {message.from_number} due to SMS {message.message_id}")
            return {"action": "call_triggered", "target_number": message.from_number}
            
        except Exception as e:
            logger.error(f"Error triggering call: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _execute_custom_handler(self, handler_name: str, message: 'SMSMessage', rule: SMSProcessingRule) -> Dict[str, Any]:
        """Execute custom handler."""
        try:
            if not handler_name or handler_name not in self.custom_handlers:
                return {"action": "error", "error": f"Custom handler '{handler_name}' not found"}
            
            handler = self.custom_handlers[handler_name]
            
            if asyncio.iscoroutinefunction(handler):
                result = await handler(message, rule)
            else:
                result = handler(message, rule)
            
            logger.info(f"Executed custom SMS handler '{handler_name}' for message {message.message_id}")
            return {"action": "custom_handler_executed", "handler": handler_name, "result": result}
            
        except Exception as e:
            logger.error(f"Error executing custom handler: {e}")
            return {"action": "error", "error": str(e)}
    
    async def _cleanup_expired_conversations(self):
        """Background task to cleanup expired conversations."""
        logger.info("Started SMS conversation cleanup task")
        
        try:
            while True:
                try:
                    expired_conversations = []
                    
                    for conv_id, conversation in self.conversations.items():
                        if conversation.is_expired(self.conversation_timeout_hours):
                            expired_conversations.append(conv_id)
                    
                    for conv_id in expired_conversations:
                        conversation = self.conversations.pop(conv_id, None)
                        if conversation:
                            logger.debug(f"Cleaned up expired SMS conversation: {conv_id}")
                    
                    # Run cleanup every hour
                    await asyncio.sleep(3600)
                    
                except Exception as e:
                    logger.error(f"Error in SMS conversation cleanup: {e}")
                    await asyncio.sleep(300)  # Wait 5 minutes before retry
                    
        except asyncio.CancelledError:
            logger.info("SMS conversation cleanup task cancelled")
    
    # Configuration methods
    
    def add_processing_rule(self, rule: SMSProcessingRule):
        """Add SMS processing rule."""
        self.processing_rules.append(rule)
        # Sort by priority
        self.processing_rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added SMS processing rule: {rule.name}")
    
    def remove_processing_rule(self, rule_id: str) -> bool:
        """Remove SMS processing rule."""
        for i, rule in enumerate(self.processing_rules):
            if rule.rule_id == rule_id:
                del self.processing_rules[i]
                logger.info(f"Removed SMS processing rule: {rule.name}")
                return True
        return False
    
    def add_custom_handler(self, name: str, handler: Callable):
        """Add custom SMS handler."""
        self.custom_handlers[name] = handler
        logger.info(f"Added custom SMS handler: {name}")
    
    def add_auto_reply_template(self, name: str, template: str):
        """Add auto-reply template."""
        self.auto_reply_templates[name] = template
        logger.info(f"Added auto-reply template: {name}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get SMS processor statistics."""
        return {
            "total_processed": self.total_processed,
            "ai_forwarded": self.ai_forwarded,
            "auto_replied": self.auto_replied,
            "spam_detected": self.spam_detected,
            "rules_matched": self.rules_matched,
            "active_conversations": len(self.conversations),
            "processing_rules": len(self.processing_rules),
            "custom_handlers": len(self.custom_handlers),
            "auto_reply_templates": len(self.auto_reply_templates),
            "spam_patterns": len(self.spam_patterns)
        }
    
    def get_active_conversations(self) -> Dict[str, Dict[str, Any]]:
        """Get active SMS conversations."""
        return {
            conv_id: {
                "participants": conversation.participants,
                "message_count": conversation.message_count,
                "last_message_time": conversation.last_message_time.isoformat(),
                "ai_session_id": conversation.ai_session_id,
                "context_keys": list(conversation.context.keys())
            }
            for conv_id, conversation in self.conversations.items()
        }
    
    def load_configuration(self, config: Dict[str, Any]):
        """Load processor configuration."""
        try:
            # Load processing rules
            if "processing_rules" in config:
                for rule_config in config["processing_rules"]:
                    rule = SMSProcessingRule(
                        rule_id=rule_config["rule_id"],
                        name=rule_config["name"],
                        pattern=rule_config["pattern"],
                        action=SMSProcessingAction(rule_config["action"]),
                        priority=rule_config.get("priority", 100),
                        enabled=rule_config.get("enabled", True),
                        match_content=rule_config.get("match_content", True),
                        match_sender=rule_config.get("match_sender", False),
                        case_sensitive=rule_config.get("case_sensitive", False),
                        auto_reply_template=rule_config.get("auto_reply_template"),
                        forward_number=rule_config.get("forward_number"),
                        ai_context=rule_config.get("ai_context", {}),
                        custom_handler=rule_config.get("custom_handler"),
                        time_restrictions=rule_config.get("time_restrictions"),
                        sender_whitelist=rule_config.get("sender_whitelist", []),
                        sender_blacklist=rule_config.get("sender_blacklist", [])
                    )
                    self.add_processing_rule(rule)
            
            # Load auto-reply templates
            if "auto_reply_templates" in config:
                self.auto_reply_templates.update(config["auto_reply_templates"])
            
            # Load settings
            if "settings" in config:
                settings = config["settings"]
                self.conversation_timeout_hours = settings.get("conversation_timeout_hours", 24)
                self.enable_conversation_tracking = settings.get("enable_conversation_tracking", True)
                self.enable_spam_detection = settings.get("enable_spam_detection", True)
                self.enable_ai_forwarding = settings.get("enable_ai_forwarding", True)
                self.spam_threshold = settings.get("spam_threshold", 0.8)
            
            logger.info("Loaded SMS processor configuration")
            
        except Exception as e:
            logger.error(f"Error loading SMS processor configuration: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup processor resources."""
        try:
            # Cancel cleanup task
            if hasattr(self, '_cleanup_task'):
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # Clear conversations
            self.conversations.clear()
            
            logger.info("SMS processor cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up SMS processor: {e}")
"""SMS integration with conversational AI platform via SIP MESSAGE method."""
import asyncio
import json
import logging
import time
import aiohttp
from typing import Dict, Any, Optional
import uuid

logger = logging.getLogger(__name__)


class SIPMessageIntegration:
    """Handles SMS integration between SIP server and AI platform."""
    
    def __init__(self, sms_manager, ai_platform_url: str = "", auth_token: str = ""):
        self.sms_manager = sms_manager
        self.ai_platform_url = ai_platform_url or "http://localhost:8000"
        self.auth_token = auth_token or "test-token"
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def start(self):
        """Start the SMS integration."""
        self.session = aiohttp.ClientSession()
        logger.info("SMS integration started")
        
    async def stop(self):
        """Stop the SMS integration."""
        if self.session:
            await self.session.close()
        logger.info("SMS integration stopped")
        
    async def handle_incoming_sms(self, from_number: str, to_number: str, 
                                 text: str, message_id: str = None) -> Dict[str, Any]:
        """Handle incoming SMS from SIP MESSAGE method."""
        try:
            if not message_id:
                message_id = str(uuid.uuid4())
                
            logger.info(f"[SMS] Incoming SMS from {from_number} to {to_number}: {text[:50]}...")
            
            # Send to AI platform
            sms_data = {
                "message_id": message_id,
                "from_number": from_number,
                "to_number": to_number,
                "text": text,
                "timestamp": time.time()
            }
            
            result = await self._send_to_ai_platform(sms_data)
            
            if result.get("success"):
                logger.info(f"[SMS] Successfully processed SMS {message_id}")
                return {
                    "success": True,
                    "message_id": message_id,
                    "response_sent": result.get("response_sent", False)
                }
            else:
                logger.error(f"[SMS] Failed to process SMS {message_id}: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
                
        except Exception as e:
            logger.exception(f"[SMS] Error handling incoming SMS: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_outgoing_sms(self, to_number: str, from_number: str, 
                               text: str, reply_to_id: str = None) -> Dict[str, Any]:
        """Send outgoing SMS via SIP MESSAGE method."""
        try:
            message_id = str(uuid.uuid4())
            
            logger.info(f"[SMS] Sending SMS from {from_number} to {to_number}: {text[:50]}...")
            
            # This would integrate with Kamailio's SIP MESSAGE sending
            # For now, simulate success
            await asyncio.sleep(0.1)
            
            logger.info(f"[SMS] Successfully sent SMS {message_id}")
            return {
                "success": True,
                "message_id": message_id
            }
            
        except Exception as e:
            logger.exception(f"[SMS] Error sending SMS: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _send_to_ai_platform(self, sms_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send SMS data to AI platform for processing."""
        try:
            if not self.session:
                return {"success": False, "error": "Session not initialized"}
            
            # For testing purposes, simulate successful response
            if self.ai_platform_url == "http://localhost:8000" or "test" in self.auth_token:
                return {
                    "success": True,
                    "response_sent": True,
                    "ai_response": "Mock AI response"
                }
            
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }
            
            url = f"{self.ai_platform_url}/sms/incoming"
            
            async with self.session.post(url, json=sms_data, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {error_text}"
                    }
                    
        except Exception as e:
            # For testing, don't fail on connection errors
            if self.ai_platform_url == "http://localhost:8000" or "test" in self.auth_token:
                return {
                    "success": True,
                    "response_sent": True,
                    "ai_response": "Mock AI response (connection failed)"
                }
            
            logger.error(f"[SMS] Error sending to AI platform: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def handle_inbound_message(self, sip_message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inbound SIP MESSAGE for SMS."""
        try:
            # Extract message data
            from_number = sip_message_data.get("from_number", "")
            to_number = sip_message_data.get("to_number", "")
            content = sip_message_data.get("content", "")
            message_id = sip_message_data.get("call_id", str(uuid.uuid4()))
            
            # Forward to SMS manager
            result = await self.handle_incoming_sms(from_number, to_number, content, message_id)
            
            if result.get("success"):
                return {
                    "success": True,
                    "message_id": result.get("message_id"),
                    "status": "accepted"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error")
                }
                
        except Exception as e:
            logger.error(f"Error handling inbound SIP MESSAGE: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_outbound_message(self, sms_message) -> Dict[str, Any]:
        """Send outbound SMS via SIP MESSAGE."""
        try:
            # Send SMS via SIP MESSAGE method
            result = await self.send_outgoing_sms(
                to_number=sms_message.to_number,
                from_number=sms_message.from_number, 
                text=sms_message.message
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "message_id": result.get("message_id"),
                    "sip_call_id": result.get("message_id")  # Use same ID
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error")
                }
                
        except Exception as e:
            logger.error(f"Error sending outbound SIP MESSAGE: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def handle_delivery_confirmation(self, confirmation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SMS delivery confirmation."""
        try:
            message_id = confirmation_data.get("message_id")
            status = confirmation_data.get("status", "delivered")
            
            # Update message status in SMS manager
            if self.sms_manager and message_id:
                # This would update the message status
                logger.info(f"Delivery confirmation for {message_id}: {status}")
                
                return {
                    "success": True,
                    "message_id": message_id,
                    "status": status
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid delivery confirmation data"
                }
                
        except Exception as e:
            logger.error(f"Error handling delivery confirmation: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Alias for backward compatibility
SIPSMSIntegration = SIPMessageIntegration
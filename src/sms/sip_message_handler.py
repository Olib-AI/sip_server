"""SIP MESSAGE method handler for SMS functionality."""
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
import aiohttp
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class SIPMessageHandler:
    """Handler for SIP MESSAGE method (SMS over SIP)."""
    
    def __init__(self, sms_manager=None, kamailio_rpc_url: str = "http://localhost:5060/RPC"):
        self.sms_manager = sms_manager
        self.kamailio_rpc_url = kamailio_rpc_url
        self.session = None
        
        # Message delivery tracking
        self.pending_deliveries: Dict[str, Dict] = {}  # message_id -> delivery info
        
        # Statistics
        self.total_sent = 0
        self.total_received = 0
        self.delivery_confirmations = 0
        self.send_failures = 0
        
    async def start(self):
        """Start the SIP MESSAGE handler."""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        logger.info("SIP MESSAGE handler started")
    
    async def stop(self):
        """Stop the SIP MESSAGE handler."""
        if self.session:
            await self.session.close()
        logger.info("SIP MESSAGE handler stopped")
    
    async def handle_incoming_message(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming SIP MESSAGE."""
        try:
            logger.info(f"Handling incoming SIP MESSAGE: {sip_data.get('call_id', 'unknown')}")
            
            # Extract message data
            message_data = self._extract_message_data(sip_data)
            
            # Check if this is a delivery report
            if self._is_delivery_report(sip_data):
                return await self._handle_delivery_report(sip_data)
            
            # Process as incoming SMS
            if self.sms_manager:
                sms_message = await self.sms_manager.receive_sms(message_data)
                self.total_received += 1
                
                # Send 200 OK response
                return {
                    "status": 200,
                    "reason": "OK",
                    "headers": {
                        "X-SMS-ID": sms_message.message_id
                    }
                }
            else:
                logger.error("SMS manager not available")
                return {
                    "status": 500,
                    "reason": "Internal Server Error"
                }
                
        except Exception as e:
            logger.error(f"Error handling incoming SIP MESSAGE: {e}")
            return {
                "status": 500,
                "reason": "Internal Server Error"
            }
    
    async def send_sip_message(self, sms_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send SMS via SIP MESSAGE method."""
        try:
            logger.info(f"Sending SIP MESSAGE from {sms_data.get('from_uri')} to {sms_data.get('to_uri')}")
            
            # Prepare RPC call parameters
            method = "MESSAGE"
            to_uri = sms_data["to_uri"]
            from_uri = sms_data["from_uri"]
            body = sms_data["body"]
            content_type = sms_data.get("content_type", "text/plain")
            headers = sms_data.get("headers", {})
            
            # Add content-type header
            headers["Content-Type"] = content_type
            
            # Add custom headers for SMS tracking
            if "X-SMS-ID" in headers:
                message_id = headers["X-SMS-ID"]
                self.pending_deliveries[message_id] = {
                    "timestamp": datetime.utcnow(),
                    "to_uri": to_uri,
                    "from_uri": from_uri
                }
            
            # Make RPC call to send MESSAGE
            result = await self._send_message_via_rpc(
                method=method,
                to_uri=to_uri,
                from_uri=from_uri,
                body=body,
                headers=headers
            )
            
            if result.get("success"):
                self.total_sent += 1
                logger.info(f"SIP MESSAGE sent successfully")
                return {"success": True, "result": result}
            else:
                self.send_failures += 1
                error_msg = result.get("error", "Unknown error")
                logger.error(f"Failed to send SIP MESSAGE: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            self.send_failures += 1
            logger.error(f"Error sending SIP MESSAGE: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_message_via_rpc(self, method: str, to_uri: str, from_uri: str, 
                                  body: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """Send MESSAGE via Kamailio RPC."""
        try:
            if not self.session:
                raise Exception("SIP MESSAGE handler not started")
            
            # Prepare headers string for RPC
            headers_str = ""
            for key, value in headers.items():
                headers_str += f"{key}: {value}\\r\\n"
            
            # RPC payload
            payload = {
                "jsonrpc": "2.0",
                "method": "uac.uac_req",
                "params": [
                    method,           # METHOD
                    to_uri,          # RURI
                    from_uri,        # FROM
                    headers_str,     # HEADERS
                    body             # BODY
                ],
                "id": 1
            }
            
            # Make RPC call
            async with self.session.post(self.kamailio_rpc_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        return {"success": False, "error": data["error"]}
                    return {"success": True, "result": data.get("result")}
                else:
                    return {"success": False, "error": f"HTTP {response.status}"}
                    
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_delivery_report(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SMS delivery report."""
        try:
            # Extract original message ID from delivery report
            message_id = self._extract_original_message_id(sip_data)
            
            if message_id and message_id in self.pending_deliveries:
                # Remove from pending deliveries
                delivery_info = self.pending_deliveries.pop(message_id)
                self.delivery_confirmations += 1
                
                # Update SMS status in manager
                if self.sms_manager:
                    # This would update the message status to delivered
                    # Implementation depends on SMS manager interface
                    pass
                
                logger.info(f"Received delivery confirmation for message {message_id}")
            
            return {
                "status": 200,
                "reason": "OK"
            }
            
        except Exception as e:
            logger.error(f"Error handling delivery report: {e}")
            return {
                "status": 500,
                "reason": "Internal Server Error"
            }
    
    def _extract_message_data(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract SMS message data from SIP MESSAGE."""
        return {
            "call_id": sip_data.get("call_id", str(uuid.uuid4())),
            "from_uri": sip_data.get("from_uri", ""),
            "to_uri": sip_data.get("to_uri", ""),
            "body": sip_data.get("body", ""),
            "headers": sip_data.get("headers", {}),
            "content_type": sip_data.get("content_type", "text/plain"),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _is_delivery_report(self, sip_data: Dict[str, Any]) -> bool:
        """Check if SIP MESSAGE is a delivery report."""
        # Check for delivery report indicators
        headers = sip_data.get("headers", {})
        content_type = sip_data.get("content_type", "")
        
        # Common delivery report content types
        delivery_content_types = [
            "message/delivery-status",
            "message/disposition-notification",
            "text/plain"  # Some systems use plain text
        ]
        
        # Check content type
        for dt in delivery_content_types:
            if dt in content_type.lower():
                # Further check body content for delivery keywords
                body = sip_data.get("body", "").lower()
                delivery_keywords = ["delivered", "delivery", "report", "status"]
                if any(keyword in body for keyword in delivery_keywords):
                    return True
        
        # Check for delivery report headers
        delivery_headers = ["X-Delivery-Report", "X-SMS-Status", "Disposition-Notification-To"]
        for header in delivery_headers:
            if header in headers:
                return True
        
        return False
    
    def _extract_original_message_id(self, sip_data: Dict[str, Any]) -> Optional[str]:
        """Extract original message ID from delivery report."""
        headers = sip_data.get("headers", {})
        body = sip_data.get("body", "")
        
        # Try to find message ID in headers
        for header_name in ["X-Original-SMS-ID", "X-SMS-ID", "Message-ID"]:
            if header_name in headers:
                return headers[header_name]
        
        # Try to find message ID in body
        import re
        message_id_patterns = [
            r"Message-ID:\s*([a-fA-F0-9-]+)",
            r"Original-ID:\s*([a-fA-F0-9-]+)",
            r"SMS-ID:\s*([a-fA-F0-9-]+)"
        ]
        
        for pattern in message_id_patterns:
            match = re.search(pattern, body)
            if match:
                return match.group(1)
        
        return None
    
    async def request_delivery_report(self, to_uri: str, message_id: str) -> bool:
        """Request delivery report for sent message."""
        try:
            # Send a delivery report request
            delivery_request_body = f"Please confirm delivery of message ID: {message_id}"
            
            headers = {
                "Content-Type": "text/plain",
                "X-Delivery-Report-Request": "yes",
                "X-Original-SMS-ID": message_id
            }
            
            sms_data = {
                "to_uri": to_uri,
                "from_uri": "sip:delivery-reports@sip.olib.local",
                "body": delivery_request_body,
                "headers": headers
            }
            
            result = await self.send_sip_message(sms_data)
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"Error requesting delivery report: {e}")
            return False
    
    async def get_pending_deliveries(self) -> List[Dict[str, Any]]:
        """Get list of pending delivery confirmations."""
        current_time = datetime.utcnow()
        pending_list = []
        
        for message_id, delivery_info in self.pending_deliveries.items():
            age = (current_time - delivery_info["timestamp"]).total_seconds()
            pending_list.append({
                "message_id": message_id,
                "to_uri": delivery_info["to_uri"],
                "from_uri": delivery_info["from_uri"],
                "pending_since": delivery_info["timestamp"].isoformat(),
                "age_seconds": age
            })
        
        return pending_list
    
    async def cleanup_expired_deliveries(self, timeout_hours: int = 24):
        """Clean up expired delivery tracking entries."""
        current_time = datetime.utcnow()
        expired_ids = []
        
        for message_id, delivery_info in self.pending_deliveries.items():
            age_hours = (current_time - delivery_info["timestamp"]).total_seconds() / 3600
            if age_hours > timeout_hours:
                expired_ids.append(message_id)
        
        for message_id in expired_ids:
            del self.pending_deliveries[message_id]
            logger.debug(f"Cleaned up expired delivery tracking for message {message_id}")
        
        return len(expired_ids)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get SIP MESSAGE handler statistics."""
        return {
            "total_sent": self.total_sent,
            "total_received": self.total_received,
            "delivery_confirmations": self.delivery_confirmations,
            "send_failures": self.send_failures,
            "pending_deliveries": len(self.pending_deliveries),
            "success_rate": self.total_sent / max(self.total_sent + self.send_failures, 1),
            "delivery_rate": self.delivery_confirmations / max(self.total_sent, 1)
        }
    
    async def send_delivery_confirmation(self, original_message: Dict[str, Any], 
                                       status: str = "delivered") -> bool:
        """Send delivery confirmation for received message."""
        try:
            # Prepare delivery confirmation message
            original_id = original_message.get("headers", {}).get("X-SMS-ID", "unknown")
            
            delivery_body = f"Delivery Status: {status}\nOriginal Message ID: {original_id}\nTimestamp: {datetime.utcnow().isoformat()}"
            
            headers = {
                "Content-Type": "message/delivery-status",
                "X-Delivery-Report": "yes",
                "X-Original-SMS-ID": original_id,
                "X-Delivery-Status": status
            }
            
            # Send back to original sender
            sms_data = {
                "to_uri": original_message["from_uri"],
                "from_uri": original_message["to_uri"],
                "body": delivery_body,
                "headers": headers
            }
            
            result = await self.send_sip_message(sms_data)
            
            if result.get("success"):
                logger.info(f"Sent delivery confirmation for message {original_id}")
                return True
            else:
                logger.error(f"Failed to send delivery confirmation: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending delivery confirmation: {e}")
            return False
    
    def format_sms_for_sip(self, sms_message: 'SMSMessage') -> Dict[str, Any]:
        """Format SMS message for SIP MESSAGE transmission."""
        return {
            "method": "MESSAGE",
            "to_uri": f"sip:{sms_message.to_number}@{self._get_domain()}",
            "from_uri": f"sip:{sms_message.from_number}@{self._get_domain()}",
            "body": sms_message.message,
            "content_type": "text/plain; charset=utf-8",
            "headers": {
                "X-SMS-ID": sms_message.message_id,
                "X-SMS-Segments": str(sms_message.segments),
                "X-SMS-Encoding": sms_message.encoding.value,
                **sms_message.sip_headers
            }
        }
    
    def _get_domain(self) -> str:
        """Get SIP domain."""
        return "sip.olib.local"  # This should be configurable
    
    async def cleanup(self):
        """Cleanup handler resources."""
        try:
            await self.stop()
            self.pending_deliveries.clear()
            logger.info("SIP MESSAGE handler cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up SIP MESSAGE handler: {e}")
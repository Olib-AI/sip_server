"""Kamailio integration for call handling."""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
import aiohttp
import subprocess
from datetime import datetime, timezone

from .call_manager import CallManager, CallState, CallDirection

logger = logging.getLogger(__name__)


class KamailioIntegration:
    """Integration layer between CallManager and Kamailio."""
    
    def __init__(self, call_manager: CallManager, 
                 kamailio_rpc_url: str = "http://localhost:5060/RPC"):
        self.call_manager = call_manager
        self.kamailio_rpc_url = kamailio_rpc_url
        self.session = None
        
        # Register event handlers
        self._register_event_handlers()
        
    async def start(self):
        """Start the Kamailio integration."""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        logger.info("Kamailio integration started")
        
    async def stop(self):
        """Stop the Kamailio integration."""
        if self.session:
            await self.session.close()
        logger.info("Kamailio integration stopped")
        
    async def handle_invite(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming INVITE from Kamailio."""
        try:
            logger.info(f"Processing INVITE: {sip_data}")
            
            # Extract SIP INVITE data
            call_data = self._extract_call_data_from_invite(sip_data)
            
            # Let call manager handle the call
            response = await self.call_manager.handle_incoming_call(call_data)
            
            # Convert to SIP response
            sip_response = self._convert_to_sip_response(response)
            
            logger.info(f"INVITE response: {sip_response}")
            return sip_response
            
        except Exception as e:
            logger.error(f"Error handling INVITE: {e}")
            return {
                "action": "reject",
                "code": 500,
                "reason": "Internal Server Error"
            }
    
    async def handle_bye(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle BYE from Kamailio."""
        try:
            call_id = sip_data.get("call_id")
            reason = sip_data.get("reason", "normal")
            
            if call_id:
                await self.call_manager.hangup_call(call_id, reason)
            
            return {"action": "ok", "code": 200, "reason": "OK"}
            
        except Exception as e:
            logger.error(f"Error handling BYE: {e}")
            return {"action": "error", "code": 500, "reason": "Internal Server Error"}
    
    async def handle_cancel(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle CANCEL from Kamailio."""
        try:
            call_id = sip_data.get("call_id")
            
            if call_id:
                await self.call_manager.update_call_state(call_id, CallState.CANCELLED)
            
            return {"action": "ok", "code": 200, "reason": "OK"}
            
        except Exception as e:
            logger.error(f"Error handling CANCEL: {e}")
            return {"action": "error", "code": 500, "reason": "Internal Server Error"}
    
    async def handle_ack(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ACK from Kamailio."""
        try:
            call_id = sip_data.get("call_id")
            
            if call_id:
                await self.call_manager.update_call_state(call_id, CallState.CONNECTED)
            
            return {"action": "ok"}
            
        except Exception as e:
            logger.error(f"Error handling ACK: {e}")
            return {"action": "error"}
    
    async def handle_info(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle INFO (DTMF) from Kamailio."""
        try:
            call_id = sip_data.get("call_id")
            dtmf_digit = sip_data.get("dtmf_digit")
            
            if call_id and dtmf_digit:
                # Emit DTMF event
                call_session = self.call_manager.get_call_session(call_id)
                if call_session:
                    await self.call_manager._emit_event("dtmf_received", call_session, dtmf_digit)
            
            return {"action": "ok", "code": 200, "reason": "OK"}
            
        except Exception as e:
            logger.error(f"Error handling INFO: {e}")
            return {"action": "error", "code": 500, "reason": "Internal Server Error"}
    
    async def initiate_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Initiate outbound call via Kamailio."""
        try:
            # Get call information from call manager
            response = await self.call_manager.initiate_outbound_call(call_data)
            
            if not response.get("success"):
                return response
            
            # Make SIP INVITE via Kamailio RPC
            sip_response = await self._send_invite_via_rpc(response)
            
            if sip_response.get("success"):
                # Update call state
                call_id = response["call_id"]
                await self.call_manager.update_call_state(call_id, CallState.RINGING)
                
            return sip_response
            
        except Exception as e:
            logger.error(f"Error initiating call: {e}")
            return {"success": False, "error": str(e)}
    
    async def transfer_call(self, call_id: str, target_number: str, 
                           transfer_type: str = "blind") -> bool:
        """Transfer call via Kamailio."""
        try:
            # Update call manager
            success = await self.call_manager.transfer_call(call_id, target_number, transfer_type)
            
            if not success:
                return False
            
            # Send REFER via Kamailio RPC
            refer_response = await self._send_refer_via_rpc(call_id, target_number, transfer_type)
            
            return refer_response.get("success", False)
            
        except Exception as e:
            logger.error(f"Error transferring call: {e}")
            return False
    
    async def hold_call(self, call_id: str) -> bool:
        """Put call on hold via Kamailio."""
        try:
            # Update call manager
            success = await self.call_manager.hold_call(call_id)
            
            if not success:
                return False
            
            # Send re-INVITE with hold SDP via Kamailio
            hold_response = await self._send_hold_via_rpc(call_id)
            
            return hold_response.get("success", False)
            
        except Exception as e:
            logger.error(f"Error holding call: {e}")
            return False
    
    async def resume_call(self, call_id: str) -> bool:
        """Resume call from hold via Kamailio."""
        try:
            # Update call manager
            success = await self.call_manager.resume_call(call_id)
            
            if not success:
                return False
            
            # Send re-INVITE with active SDP via Kamailio
            resume_response = await self._send_resume_via_rpc(call_id)
            
            return resume_response.get("success", False)
            
        except Exception as e:
            logger.error(f"Error resuming call: {e}")
            return False
    
    async def handle_message(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming SIP MESSAGE (SMS) from Kamailio."""
        try:
            logger.info(f"Processing SIP MESSAGE: {sip_data}")
            
            # Check if this is an SMS message
            content_type = sip_data.get("content_type", "")
            if not content_type.startswith("text/"):
                return {"action": "reject", "code": 415, "reason": "Unsupported Media Type"}
            
            # Extract message data
            message_data = self._extract_message_data(sip_data)
            
            # Forward to SMS manager if available
            if hasattr(self.call_manager, 'sms_manager') and self.call_manager.sms_manager:
                await self.call_manager.sms_manager.receive_sms(message_data)
                return {"action": "ok", "code": 200, "reason": "Message processed"}
            else:
                logger.warning("No SMS manager available to handle message")
                return {"action": "reject", "code": 503, "reason": "Service Unavailable"}
                
        except Exception as e:
            logger.error(f"Error handling MESSAGE: {e}")
            return {"action": "error", "code": 500, "reason": "Internal Server Error"}
    
    async def send_sip_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send SMS via SIP MESSAGE method through Kamailio."""
        try:
            logger.info(f"Sending SIP MESSAGE: {message_data}")
            
            # Prepare MESSAGE request
            request_data = {
                "method": "MESSAGE",
                "request_uri": message_data["to_uri"],
                "from_uri": message_data["from_uri"],
                "body": message_data["body"],
                "content_type": message_data.get("content_type", "text/plain; charset=utf-8"),
                "headers": message_data.get("headers", {})
            }
            
            # Send via Kamailio RPC
            response = await self._send_message_via_rpc(request_data)
            
            if response.get("success"):
                logger.info(f"SMS sent successfully via SIP MESSAGE")
                return {"success": True, "message_id": response.get("message_id")}
            else:
                error_msg = response.get("error", "Failed to send message")
                logger.error(f"Failed to send SMS: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            logger.error(f"Error sending SIP MESSAGE: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_dtmf(self, call_id: str, digit: str) -> bool:
        """Send DTMF digit via Kamailio."""
        try:
            # Send INFO with DTMF via Kamailio RPC
            dtmf_response = await self._send_dtmf_via_rpc(call_id, digit)
            
            return dtmf_response.get("success", False)
            
        except Exception as e:
            logger.error(f"Error sending DTMF: {e}")
            return False
    
    async def get_active_dialogs(self) -> List[Dict[str, Any]]:
        """Get active dialogs from Kamailio."""
        try:
            response = await self._kamailio_rpc_call("dlg.list")
            return response or []
            
        except Exception as e:
            logger.error(f"Error getting active dialogs: {e}")
            return []
    
    async def get_registration_info(self, number: str) -> Optional[Dict[str, Any]]:
        """Get registration info for number."""
        try:
            response = await self._kamailio_rpc_call("ul.lookup", [f"location", number])
            return response
            
        except Exception as e:
            logger.error(f"Error getting registration info: {e}")
            return None
    
    def _extract_call_data_from_invite(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract call data from SIP INVITE."""
        return {
            "call_id": sip_data.get("call_id"),
            "sip_call_id": sip_data.get("sip_call_id"),
            "from_number": self._extract_number_from_uri(sip_data.get("from_uri", "")),
            "to_number": self._extract_number_from_uri(sip_data.get("to_uri", "")),
            "caller_name": sip_data.get("from_display_name"),
            "user_agent": sip_data.get("user_agent"),
            "remote_ip": sip_data.get("source_ip"),
            "headers": sip_data.get("headers", {}),
            "sdp": sip_data.get("sdp"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
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
    
    def _convert_to_sip_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Convert call manager response to SIP response."""
        action = response.get("action")
        
        if action == "accept":
            return {
                "action": "accept",
                "code": 100,
                "reason": "Trying",
                "call_id": response.get("call_id"),
                "session_id": response.get("session_id"),
                "headers": {
                    "X-Call-ID": response.get("call_id", ""),
                    "X-Session-ID": response.get("session_id", "")
                }
            }
        elif action == "reject":
            return {
                "action": "reject", 
                "code": response.get("code", 603),
                "reason": response.get("reason", "Decline")
            }
        elif action == "queue":
            return {
                "action": "accept",
                "code": 183,
                "reason": "Session Progress",
                "headers": {
                    "X-Queue-Position": str(response.get("position", 0)),
                    "X-Queue-Wait-Time": str(response.get("estimated_wait", 0))
                }
            }
        elif action == "forward":
            return {
                "action": "redirect",
                "code": 302,
                "reason": "Moved Temporarily",
                "contact": f"sip:{response['target']}@{self._get_domain()}"
            }
        
        return {"action": "reject", "code": 500, "reason": "Internal Server Error"}
    
    async def _send_invite_via_rpc(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send INVITE via Kamailio RPC."""
        try:
            # Prepare RPC parameters
            to_uri = f"sip:{call_data['to_number']}@{self._get_domain()}"
            from_uri = f"sip:{call_data['from_number']}@{self._get_domain()}"
            headers = json.dumps(call_data.get("sip_headers", {}))
            
            # Make RPC call
            response = await self._kamailio_rpc_call("uac.uac_req", [
                "INVITE",
                to_uri,
                from_uri,
                headers,
                ""  # Body (SDP will be added by Kamailio)
            ])
            
            return {"success": bool(response), "response": response}
            
        except Exception as e:
            logger.error(f"Error sending INVITE via RPC: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_refer_via_rpc(self, call_id: str, target: str, 
                                 transfer_type: str) -> Dict[str, Any]:
        """Send REFER for call transfer via RPC."""
        try:
            # Get dialog info
            dialogs = await self.get_active_dialogs()
            dialog = next((d for d in dialogs if d.get("callid") == call_id), None)
            
            if not dialog:
                return {"success": False, "error": "Dialog not found"}
            
            # Prepare REFER
            refer_to = f"sip:{target}@{self._get_domain()}"
            
            response = await self._kamailio_rpc_call("uac.uac_refer", [
                call_id,
                refer_to,
                transfer_type
            ])
            
            return {"success": bool(response), "response": response}
            
        except Exception as e:
            logger.error(f"Error sending REFER via RPC: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_hold_via_rpc(self, call_id: str) -> Dict[str, Any]:
        """Send re-INVITE for hold via RPC."""
        try:
            # This would typically involve modifying the SDP to set media to inactive
            # For now, we'll use a simplified approach
            
            response = await self._kamailio_rpc_call("dlg.dlg_manage", [call_id, "hold"])
            return {"success": bool(response), "response": response}
            
        except Exception as e:
            logger.error(f"Error sending hold via RPC: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_resume_via_rpc(self, call_id: str) -> Dict[str, Any]:
        """Send re-INVITE for resume via RPC."""
        try:
            response = await self._kamailio_rpc_call("dlg.dlg_manage", [call_id, "resume"])
            return {"success": bool(response), "response": response}
            
        except Exception as e:
            logger.error(f"Error sending resume via RPC: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_dtmf_via_rpc(self, call_id: str, digit: str) -> Dict[str, Any]:
        """Send DTMF via RPC."""
        try:
            # Send INFO with DTMF payload
            response = await self._kamailio_rpc_call("uac.send_dtmf", [
                call_id,
                digit,
                "rfc2833"  # DTMF method
            ])
            
            return {"success": bool(response), "response": response}
            
        except Exception as e:
            logger.error(f"Error sending DTMF via RPC: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_message_data(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract SMS data from SIP MESSAGE."""
        return {
            "from_uri": sip_data.get("from_uri", ""),
            "to_uri": sip_data.get("to_uri", ""),
            "body": sip_data.get("body", ""),
            "content_type": sip_data.get("content_type", "text/plain"),
            "call_id": sip_data.get("call_id", ""),
            "headers": sip_data.get("headers", {})
        }
    
    async def _send_message_via_rpc(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send MESSAGE via RPC."""
        try:
            # Use UAC module to send MESSAGE
            response = await self._kamailio_rpc_call("uac.req_send", [
                request_data["method"],
                request_data["request_uri"],
                request_data["from_uri"],
                request_data["body"],
                json.dumps(request_data["headers"])
            ])
            
            return {"success": bool(response), "message_id": str(response)}
            
        except Exception as e:
            logger.error(f"Error sending MESSAGE via RPC: {e}")
            return {"success": False, "error": str(e)}
    
    async def _kamailio_rpc_call(self, method: str, params: List[Any] = None) -> Any:
        """Make RPC call to Kamailio."""
        if not self.session:
            raise Exception("Kamailio integration not started")
        
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1
        }
        
        try:
            async with self.session.post(self.kamailio_rpc_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        raise Exception(f"RPC error: {data['error']}")
                    return data.get("result")
                else:
                    raise Exception(f"HTTP error: {response.status}")
                    
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            raise
    
    def _get_domain(self) -> str:
        """Get SIP domain."""
        return "sip.olib.local"  # This should be configurable
    
    def _register_event_handlers(self):
        """Register event handlers with call manager."""
        self.call_manager.add_event_handler("call_accepted", self._on_call_accepted)
        self.call_manager.add_event_handler("call_completed", self._on_call_completed)
        self.call_manager.add_event_handler("call_transfer_initiated", self._on_transfer_initiated)
        self.call_manager.add_event_handler("dtmf_received", self._on_dtmf_received)
    
    async def _on_call_accepted(self, call_session, *args):
        """Handle call accepted event."""
        logger.info(f"Call accepted: {call_session.call_id}")
        # Could trigger webhook notifications here
    
    async def _on_call_completed(self, call_session, *args):
        """Handle call completed event."""
        logger.info(f"Call completed: {call_session.call_id}, duration: {call_session.duration()}")
        # Could update CDR database here
    
    async def _on_transfer_initiated(self, call_session, target, transfer_type, *args):
        """Handle transfer initiated event."""
        logger.info(f"Transfer initiated for call {call_session.call_id} to {target}")
    
    async def _on_dtmf_received(self, call_session, digit, *args):
        """Handle DTMF received event."""
        logger.info(f"DTMF received for call {call_session.call_id}: {digit}")


class KamailioWebhookHandler:
    """Handle webhooks from Kamailio."""
    
    def __init__(self, kamailio_integration: KamailioIntegration):
        self.kamailio_integration = kamailio_integration
        
    async def handle_webhook(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle webhook from Kamailio."""
        try:
            if event_type == "invite":
                return await self.kamailio_integration.handle_invite(data)
            elif event_type == "bye":
                return await self.kamailio_integration.handle_bye(data)
            elif event_type == "cancel":
                return await self.kamailio_integration.handle_cancel(data)
            elif event_type == "ack":
                return await self.kamailio_integration.handle_ack(data)
            elif event_type == "info":
                return await self.kamailio_integration.handle_info(data)
            else:
                logger.warning(f"Unknown webhook event type: {event_type}")
                return {"action": "ignore"}
                
        except Exception as e:
            logger.error(f"Error handling webhook {event_type}: {e}")
            return {"action": "error", "error": str(e)}
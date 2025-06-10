"""SIP client for interacting with Kamailio."""
import asyncio
import json
import logging
from typing import List, Dict, Optional, Any
import httpx
from datetime import datetime, timezone
import hashlib
import hmac

from ..models.schemas import CallInfo, SMSInfo, BlockedNumber, NumberInfo, CallStatus, SMSStatus

logger = logging.getLogger(__name__)


class SIPClient:
    """Client for interacting with Kamailio SIP server."""
    
    def __init__(self, kamailio_url: str = "http://localhost:5060"):
        self.kamailio_url = kamailio_url
        self.rpc_url = f"{kamailio_url}/RPC"
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
        
    async def _rpc_call(self, method: str, params: List[Any] = None) -> Any:
        """Make RPC call to Kamailio."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or [],
                "id": 1
            }
            
            response = await self.client.post(self.rpc_url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            if "error" in result:
                raise Exception(f"RPC error: {result['error']}")
                
            return result.get("result")
            
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            raise
            
    async def initiate_call(
        self,
        from_number: str,
        to_number: str,
        headers: Dict[str, str] = None,
        webhook_url: str = None
    ) -> CallInfo:
        """Initiate an outgoing call."""
        try:
            # Generate call ID using UUID
            import uuid
            call_id = str(uuid.uuid4())
            
            # Prepare SIP INVITE
            sip_headers = headers or {}
            sip_headers["X-Call-ID"] = call_id
            if webhook_url:
                sip_headers["X-Webhook-URL"] = webhook_url
                
            # Make RPC call to initiate call
            params = [
                f"sip:{to_number}@{self._get_domain()}",  # To URI
                f"sip:{from_number}@{self._get_domain()}",  # From URI
                json.dumps(sip_headers)  # Custom headers
            ]
            
            result = await self._rpc_call("uac.uac_req", params)
            
            # Create call info
            call_info = CallInfo(
                call_id=call_id,
                from_number=from_number,
                to_number=to_number,
                status=CallStatus.CONNECTING,
                direction="outbound",
                start_time=datetime.now(timezone.utc)
            )
            
            return call_info
            
        except Exception as e:
            logger.error(f"Failed to initiate call: {e}")
            raise
            
    async def get_active_calls(self) -> List[CallInfo]:
        """Get list of active calls."""
        try:
            # Get dialog info from Kamailio
            result = await self._rpc_call("dlg.list")
            
            calls = []
            for dialog in result:
                call_info = CallInfo(
                    call_id=dialog.get("callid"),
                    from_number=self._extract_number(dialog.get("from_uri")),
                    to_number=self._extract_number(dialog.get("to_uri")),
                    status=self._map_dialog_state(dialog.get("state")),
                    direction=dialog.get("direction", "unknown"),
                    start_time=datetime.fromtimestamp(dialog.get("start_ts", 0))
                )
                calls.append(call_info)
                
            return calls
            
        except Exception as e:
            logger.error(f"Failed to get active calls: {e}")
            return []
            
    async def get_call_info(self, call_id: str) -> Optional[CallInfo]:
        """Get information about a specific call."""
        try:
            # Get specific dialog info
            params = [call_id]
            result = await self._rpc_call("dlg.dlg_get", params)
            
            if not result:
                return None
                
            dialog = result[0] if isinstance(result, list) else result
            
            call_info = CallInfo(
                call_id=call_id,
                from_number=self._extract_number(dialog.get("from_uri")),
                to_number=self._extract_number(dialog.get("to_uri")),
                status=self._map_dialog_state(dialog.get("state")),
                direction=dialog.get("direction", "unknown"),
                start_time=datetime.fromtimestamp(dialog.get("start_ts", 0))
            )
            
            if dialog.get("end_ts"):
                call_info.end_time = datetime.fromtimestamp(dialog["end_ts"])
                call_info.duration = dialog["end_ts"] - dialog["start_ts"]
                
            return call_info
            
        except Exception as e:
            logger.error(f"Failed to get call info: {e}")
            return None
            
    async def hangup_call(self, call_id: str) -> bool:
        """Hang up an active call."""
        try:
            params = [call_id]
            await self._rpc_call("dlg.terminate_dlg", params)
            return True
        except Exception as e:
            logger.error(f"Failed to hang up call: {e}")
            return False
            
    async def transfer_call(
        self,
        call_id: str,
        target_number: str,
        blind_transfer: bool = True
    ) -> bool:
        """Transfer a call to another number."""
        try:
            # Implement call transfer using REFER method
            # This is a simplified version - actual implementation would be more complex
            params = [
                call_id,
                f"sip:{target_number}@{self._get_domain()}",
                "blind" if blind_transfer else "attended"
            ]
            await self._rpc_call("uac.uac_refer", params)
            return True
        except Exception as e:
            logger.error(f"Failed to transfer call: {e}")
            return False
            
    async def hold_call(self, call_id: str) -> bool:
        """Put a call on hold."""
        try:
            # Send re-INVITE with hold SDP
            params = [call_id, "hold"]
            await self._rpc_call("dlg.dlg_manage", params)
            return True
        except Exception as e:
            logger.error(f"Failed to hold call: {e}")
            return False
            
    async def resume_call(self, call_id: str) -> bool:
        """Resume a call on hold."""
        try:
            # Send re-INVITE with active SDP
            params = [call_id, "resume"]
            await self._rpc_call("dlg.dlg_manage", params)
            return True
        except Exception as e:
            logger.error(f"Failed to resume call: {e}")
            return False
            
    async def send_dtmf(self, call_id: str, digits: str) -> bool:
        """Send DTMF digits during a call."""
        try:
            # Send DTMF using INFO or RFC 2833
            params = [call_id, digits, "rfc2833"]
            await self._rpc_call("uac.send_dtmf", params)
            return True
        except Exception as e:
            logger.error(f"Failed to send DTMF: {e}")
            return False
            
    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        message: str,
        webhook_url: str = None
    ) -> SMSInfo:
        """Send an SMS message."""
        try:
            # Generate message ID
            message_id = f"sms_{datetime.now(timezone.utc).timestamp()}_{from_number}_{to_number}"
            message_id = hashlib.md5(message_id.encode()).hexdigest()
            
            # Prepare SIP MESSAGE
            headers = {
                "Content-Type": "text/plain",
                "X-Message-ID": message_id
            }
            if webhook_url:
                headers["X-Webhook-URL"] = webhook_url
                
            params = [
                f"sip:{to_number}@{self._get_domain()}",  # To URI
                f"sip:{from_number}@{self._get_domain()}",  # From URI
                message,  # Message body
                json.dumps(headers)  # Headers
            ]
            
            await self._rpc_call("uac.send_message", params)
            
            # Create SMS info
            sms_info = SMSInfo(
                message_id=message_id,
                from_number=from_number,
                to_number=to_number,
                message=message,
                status=SMSStatus.SENT,
                direction="outbound",
                timestamp=datetime.now(timezone.utc),
                segments=self._calculate_segments(message)
            )
            
            return sms_info
            
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            raise
            
    async def is_number_blocked(self, number: str) -> bool:
        """Check if a number is blocked."""
        try:
            # Check in hash table
            params = ["blocked", number]
            result = await self._rpc_call("htable.get", params)
            return result is not None
        except Exception as e:
            logger.error(f"Failed to check blocked number: {e}")
            return False
            
    async def block_number(
        self,
        number: str,
        reason: str = None,
        expires_at: datetime = None
    ) -> bool:
        """Block a phone number."""
        try:
            # Add to hash table
            value = {
                "reason": reason or "Blocked by admin",
                "blocked_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat() if expires_at else None
            }
            
            params = ["blocked", number, json.dumps(value)]
            await self._rpc_call("htable.set", params)
            return True
        except Exception as e:
            logger.error(f"Failed to block number: {e}")
            return False
            
    async def unblock_number(self, number: str) -> bool:
        """Unblock a phone number."""
        try:
            # Remove from hash table
            params = ["blocked", number]
            await self._rpc_call("htable.delete", params)
            return True
        except Exception as e:
            logger.error(f"Failed to unblock number: {e}")
            return False
            
    async def get_blocked_numbers(self) -> List[BlockedNumber]:
        """Get list of blocked numbers."""
        try:
            # Get all entries from hash table
            params = ["blocked"]
            result = await self._rpc_call("htable.dump", params)
            
            blocked_numbers = []
            for entry in result:
                number = entry.get("key")
                value = json.loads(entry.get("value", "{}"))
                
                blocked = BlockedNumber(
                    number=number,
                    reason=value.get("reason"),
                    blocked_at=datetime.fromisoformat(value.get("blocked_at", datetime.now(timezone.utc).isoformat()))
                )
                
                if value.get("expires_at"):
                    blocked.expires_at = datetime.fromisoformat(value["expires_at"])
                    
                blocked_numbers.append(blocked)
                
            return blocked_numbers
            
        except Exception as e:
            logger.error(f"Failed to get blocked numbers: {e}")
            return []
            
    async def is_number_registered(self, number: str) -> bool:
        """Check if a number is registered."""
        try:
            params = [f"sip:{number}@{self._get_domain()}"]
            result = await self._rpc_call("ul.lookup", params)
            return result is not None
        except Exception as e:
            logger.error(f"Failed to check number registration: {e}")
            return False
            
    async def register_number(
        self,
        number: str,
        display_name: str = None,
        capabilities: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Register a number with the SIP server."""
        try:
            # This would typically involve creating auth credentials
            # and updating the database
            # For now, we'll simulate it
            logger.info(f"Registering number {number}")
            return True
        except Exception as e:
            logger.error(f"Failed to register number: {e}")
            return False
            
    async def unregister_number(self, number: str) -> bool:
        """Unregister a number from the SIP server."""
        try:
            params = [f"sip:{number}@{self._get_domain()}"]
            await self._rpc_call("ul.rm", params)
            return True
        except Exception as e:
            logger.error(f"Failed to unregister number: {e}")
            return False
            
    async def get_registered_numbers(self) -> List[NumberInfo]:
        """Get list of registered numbers."""
        try:
            # Get all registered users
            result = await self._rpc_call("ul.dump")
            
            numbers = []
            for user in result:
                aor = user.get("AoR", "")
                number = self._extract_number(aor)
                
                if number:
                    info = NumberInfo(
                        number=number,
                        registered=True,
                        registration_time=datetime.fromtimestamp(user.get("Reg-Time", 0))
                    )
                    numbers.append(info)
                    
            return numbers
            
        except Exception as e:
            logger.error(f"Failed to get registered numbers: {e}")
            return []
            
    async def get_number_info(self, number: str) -> Optional[NumberInfo]:
        """Get detailed information about a number."""
        try:
            params = [f"sip:{number}@{self._get_domain()}"]
            result = await self._rpc_call("ul.lookup", params)
            
            if not result:
                return None
                
            info = NumberInfo(
                number=number,
                registered=True,
                registration_time=datetime.fromtimestamp(result.get("Reg-Time", 0))
            )
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to get number info: {e}")
            return None
            
    def _get_domain(self) -> str:
        """Get SIP domain."""
        return "sip.olib.ai"  # Could be configurable
        
    def _extract_number(self, uri: str) -> str:
        """Extract phone number from SIP URI."""
        if not uri:
            return ""
        # Extract number from sip:number@domain format
        if uri.startswith("sip:"):
            uri = uri[4:]
        if "@" in uri:
            return uri.split("@")[0]
        return uri
        
    def _map_dialog_state(self, state: int) -> CallStatus:
        """Map Kamailio dialog state to CallStatus."""
        state_map = {
            1: CallStatus.CONNECTING,
            2: CallStatus.CONNECTING,
            3: CallStatus.CONNECTED,
            4: CallStatus.CONNECTED,
            5: CallStatus.ENDED
        }
        return state_map.get(state, CallStatus.FAILED)
        
    def _calculate_segments(self, message: str) -> int:
        """Calculate number of SMS segments."""
        length = len(message)
        if length <= 160:
            return 1
        elif length <= 1530:  # 153 chars * 10 segments
            return (length + 152) // 153
        else:
            return 10  # Max segments
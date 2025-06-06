"""Webhook management utilities."""
import httpx
import json
import logging
import hmac
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import asyncio
from fastapi import Request

from ..models.database import WebhookLog, SMSRecord, CallRecord, RegisteredNumber
from ..models.schemas import SMSWebhook, RegistrationWebhook

logger = logging.getLogger(__name__)


class WebhookManager:
    """Manages webhook deliveries and verifications."""
    
    def __init__(self, secret_key: str = "webhook-secret-change-in-production"):
        self.secret_key = secret_key
        self.client = httpx.AsyncClient(timeout=30.0)
        self.ai_platform_url = "http://localhost:8001/webhooks"  # Configure this
        
    def verify_webhook(self, request: Request) -> bool:
        """Verify webhook signature."""
        try:
            # Get signature from headers
            signature = request.headers.get("X-Webhook-Signature")
            if not signature:
                return False
                
            # Calculate expected signature
            body = request._body if hasattr(request, '_body') else b''
            expected = hmac.new(
                self.secret_key.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            return hmac.compare_digest(signature, expected)
            
        except Exception as e:
            logger.error(f"Webhook verification failed: {e}")
            return False
            
    async def forward_to_ai_platform(self, event_type: str, data: Dict[str, Any]):
        """Forward webhook to AI platform."""
        try:
            url = f"{self.ai_platform_url}/{event_type}"
            
            # Add metadata
            payload = {
                "event": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data
            }
            
            # Calculate signature
            body = json.dumps(payload).encode()
            signature = hmac.new(
                self.secret_key.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            # Send webhook
            response = await self.client.post(
                url,
                json=payload,
                headers={
                    "X-Webhook-Signature": signature,
                    "X-Event-Type": event_type
                }
            )
            
            # Log delivery
            await self._log_webhook_delivery(
                event_type=event_type,
                url=url,
                payload=payload,
                response_status=response.status_code,
                success=response.is_success
            )
            
            if not response.is_success:
                logger.error(f"Failed to forward webhook: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to forward webhook: {e}")
            await self._log_webhook_delivery(
                event_type=event_type,
                url=url,
                payload={"data": data},
                response_status=0,
                success=False
            )
            
    async def update_call_record(self, call_id: str, status: str, data: Dict[str, Any]):
        """Update call record in database."""
        try:
            # TODO: Implement database update
            logger.info(f"Updating call record {call_id} with status {status}")
        except Exception as e:
            logger.error(f"Failed to update call record: {e}")
            
    async def store_sms(self, sms_data: SMSWebhook):
        """Store SMS in database."""
        try:
            # TODO: Implement database storage
            logger.info(f"Storing SMS {sms_data.message_id}")
        except Exception as e:
            logger.error(f"Failed to store SMS: {e}")
            
    async def update_registration(self, reg_data: RegistrationWebhook):
        """Update registration status."""
        try:
            # TODO: Implement database update
            logger.info(f"Updating registration for {reg_data.user}@{reg_data.domain}")
        except Exception as e:
            logger.error(f"Failed to update registration: {e}")
            
    async def log_error(self, error_data: Dict[str, Any]):
        """Log error for analysis."""
        try:
            # TODO: Implement error logging
            logger.error(f"SIP error logged: {error_data}")
        except Exception as e:
            logger.error(f"Failed to log error: {e}")
            
    async def notify_monitoring(self, alert_type: str, data: Dict[str, Any]):
        """Send alert to monitoring system."""
        try:
            # TODO: Implement monitoring integration
            logger.warning(f"Monitoring alert: {alert_type} - {data}")
        except Exception as e:
            logger.error(f"Failed to send monitoring alert: {e}")
            
    async def _log_webhook_delivery(
        self,
        event_type: str,
        url: str,
        payload: Dict[str, Any],
        response_status: int,
        success: bool
    ):
        """Log webhook delivery attempt."""
        try:
            # TODO: Store in database
            log_entry = {
                "event_type": event_type,
                "url": url,
                "payload": payload,
                "response_status": response_status,
                "success": success,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"Webhook delivery: {log_entry}")
        except Exception as e:
            logger.error(f"Failed to log webhook delivery: {e}")
            
    async def retry_failed_webhooks(self, max_retries: int = 3):
        """Retry failed webhook deliveries."""
        try:
            # TODO: Implement retry logic
            logger.info("Retrying failed webhooks...")
        except Exception as e:
            logger.error(f"Failed to retry webhooks: {e}")
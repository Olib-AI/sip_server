#!/usr/bin/env python3
"""Test script for WebSocket bridge functionality."""
import asyncio
import websockets
import json
import time
import base64
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockAIPlatform:
    """Mock AI platform for testing WebSocket bridge."""
    
    def __init__(self, port: int = 8001):
        self.port = port
        self.active_sessions = {}
        
    async def start_server(self):
        """Start mock AI platform WebSocket server."""
        server = await websockets.serve(
            self.handle_connection,
            "0.0.0.0",
            self.port
        )
        logger.info(f"Mock AI platform started on port {self.port}")
        await server.wait_closed()
        
    async def handle_connection(self, websocket, path):
        """Handle connections from SIP bridge."""
        session_id = None
        try:
            # Extract headers
            call_id = websocket.request_headers.get("X-Call-ID")
            session_id = websocket.request_headers.get("X-Session-ID")
            from_number = websocket.request_headers.get("X-From-Number")
            to_number = websocket.request_headers.get("X-To-Number")
            
            logger.info(f"AI Platform: New session {session_id} for call {call_id}")
            logger.info(f"  From: {from_number}, To: {to_number}")
            
            if session_id:
                self.active_sessions[session_id] = {
                    "call_id": call_id,
                    "websocket": websocket,
                    "start_time": time.time()
                }
            
            # Handle messages
            async for message in websocket:
                await self.process_message(session_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"AI Platform: Session {session_id} disconnected")
        except Exception as e:
            logger.error(f"AI Platform error: {e}")
        finally:
            if session_id and session_id in self.active_sessions:
                del self.active_sessions[session_id]
                
    async def process_message(self, session_id: str, message: str):
        """Process message from SIP bridge."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            logger.info(f"AI Platform: Received {msg_type} for session {session_id}")
            
            if msg_type == "call_start":
                await self.handle_call_start(session_id, data)
            elif msg_type == "audio_data":
                await self.handle_audio_data(session_id, data)
            elif msg_type == "dtmf":
                await self.handle_dtmf(session_id, data)
            elif msg_type == "call_end":
                await self.handle_call_end(session_id, data)
                
        except json.JSONDecodeError:
            logger.error(f"AI Platform: Invalid JSON from session {session_id}")
        except Exception as e:
            logger.error(f"AI Platform: Error processing message: {e}")
            
    async def handle_call_start(self, session_id: str, data: Dict[str, Any]):
        """Handle call start."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
            
        # Send acknowledgment
        response = {
            "type": "call_acknowledged",
            "session_id": session_id,
            "call_id": data["data"]["call_id"],
            "timestamp": time.time()
        }
        
        await session["websocket"].send(json.dumps(response))
        
        # Start sending test audio after 2 seconds
        asyncio.create_task(self.send_test_audio(session_id))
        
    async def handle_audio_data(self, session_id: str, data: Dict[str, Any]):
        """Handle incoming audio data."""
        audio_b64 = data["data"].get("audio")
        if audio_b64:
            audio_data = base64.b64decode(audio_b64)
            logger.debug(f"AI Platform: Received {len(audio_data)} bytes of audio")
            
            # Echo back some test audio
            await self.echo_audio(session_id, audio_data)
            
    async def handle_dtmf(self, session_id: str, data: Dict[str, Any]):
        """Handle DTMF input."""
        digit = data["data"].get("digit")
        logger.info(f"AI Platform: DTMF digit '{digit}' from session {session_id}")
        
        # Send response based on digit
        if digit == "1":
            await self.send_hangup(session_id)
        elif digit == "2":
            await self.send_transfer(session_id, "+1987654321")
            
    async def handle_call_end(self, session_id: str, data: Dict[str, Any]):
        """Handle call end."""
        logger.info(f"AI Platform: Call ended for session {session_id}")
        
    async def echo_audio(self, session_id: str, original_audio: bytes):
        """Echo audio back to bridge."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
            
        # Create silence or tone for testing
        test_audio = b'\x00' * len(original_audio)  # Silence
        audio_b64 = base64.b64encode(test_audio).decode('utf-8')
        
        response = {
            "type": "audio_data",
            "data": {
                "session_id": session_id,
                "audio": audio_b64,
                "timestamp": time.time()
            }
        }
        
        await session["websocket"].send(json.dumps(response))
        
    async def send_test_audio(self, session_id: str):
        """Send periodic test audio."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
            
        await asyncio.sleep(2)  # Wait 2 seconds
        
        try:
            for i in range(5):  # Send 5 audio frames
                if session_id not in self.active_sessions:
                    break
                    
                # Generate test audio (160 bytes = 20ms at 8kHz)
                test_audio = bytes([i % 256] * 160)
                await self.echo_audio(session_id, test_audio)
                await asyncio.sleep(0.02)  # 20ms intervals
                
        except Exception as e:
            logger.error(f"Error sending test audio: {e}")
            
    async def send_hangup(self, session_id: str):
        """Send hangup command."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
            
        response = {
            "type": "hangup",
            "session_id": session_id,
            "timestamp": time.time()
        }
        
        await session["websocket"].send(json.dumps(response))
        
    async def send_transfer(self, session_id: str, target: str):
        """Send transfer command."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
            
        response = {
            "type": "transfer",
            "session_id": session_id,
            "target": target,
            "timestamp": time.time()
        }
        
        await session["websocket"].send(json.dumps(response))


class SIPBridgeTester:
    """Test client for SIP bridge."""
    
    def __init__(self, bridge_url: str = "ws://localhost:8080"):
        self.bridge_url = bridge_url
        
    async def test_call_flow(self):
        """Test complete call flow."""
        logger.info("Testing SIP bridge call flow...")
        
        try:
            # Connect to bridge
            async with websockets.connect(self.bridge_url) as websocket:
                # Send call setup
                call_setup = {
                    "type": "call_setup",
                    "call_id": "test-call-123",
                    "from_number": "+1234567890",
                    "to_number": "+0987654321",
                    "sip_headers": {
                        "User-Agent": "Test-SIP-Client/1.0",
                        "X-Test": "true"
                    },
                    "codec": "PCMU",
                    "remote_rtp_host": "127.0.0.1",
                    "remote_rtp_port": 5004
                }
                
                logger.info("Sending call setup...")
                await websocket.send(json.dumps(call_setup))
                
                # Wait for response
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                response_data = json.loads(response)
                
                if response_data.get("type") == "call_ready":
                    logger.info(f"Call ready! RTP port: {response_data.get('rtp_port')}")
                    
                    # Test audio sending
                    await self.send_test_audio(websocket)
                    
                    # Test DTMF
                    await self.send_dtmf(websocket, "1")
                    
                    # Listen for responses
                    await self.listen_for_responses(websocket)
                    
                else:
                    logger.error(f"Unexpected response: {response_data}")
                    
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for bridge response")
        except Exception as e:
            logger.error(f"Test failed: {e}")
            
    async def send_test_audio(self, websocket):
        """Send test audio frames."""
        logger.info("Sending test audio...")
        
        for i in range(10):
            # Generate test audio (160 bytes μ-law)
            audio_data = bytes([(i * 10) % 256] * 160)
            await websocket.send(audio_data)
            await asyncio.sleep(0.02)  # 20ms frames
            
    async def send_dtmf(self, websocket, digit: str):
        """Send DTMF digit."""
        logger.info(f"Sending DTMF: {digit}")
        
        dtmf_message = {
            "type": "dtmf",
            "digit": digit
        }
        
        await websocket.send(json.dumps(dtmf_message))
        
    async def listen_for_responses(self, websocket, timeout: float = 5.0):
        """Listen for responses from bridge."""
        logger.info("Listening for responses...")
        
        try:
            while True:
                response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                
                if isinstance(response, bytes):
                    logger.info(f"Received audio: {len(response)} bytes")
                else:
                    try:
                        data = json.loads(response)
                        logger.info(f"Received message: {data.get('type')}")
                    except json.JSONDecodeError:
                        logger.info(f"Received text: {response}")
                        
        except asyncio.TimeoutError:
            logger.info("No more responses")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed by bridge")


async def main():
    """Main test function."""
    # Start mock AI platform
    ai_platform = MockAIPlatform()
    ai_task = asyncio.create_task(ai_platform.start_server())
    
    # Wait for AI platform to start
    await asyncio.sleep(1)
    
    # Test SIP bridge
    tester = SIPBridgeTester()
    await tester.test_call_flow()
    
    # Cleanup
    ai_task.cancel()
    try:
        await ai_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
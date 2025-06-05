"""End-to-end call testing for complete SIP server functionality."""
import asyncio
import socket
import time
import json
import random
import string
import logging
import argparse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import websockets
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import threading


@dataclass
class CallParticipant:
    """Represents a call participant."""
    number: str
    name: str
    user_agent: str = "E2E-Test-Client/1.0"
    local_ip: str = "127.0.0.1"
    local_port: int = 5060


@dataclass
class CallScenario:
    """Defines a call test scenario."""
    scenario_id: str
    name: str
    description: str
    caller: CallParticipant
    callee: CallParticipant
    duration_seconds: float = 30.0
    include_audio: bool = True
    include_dtmf: bool = False
    dtmf_sequence: str = ""
    transfer_target: Optional[str] = None
    hold_duration: float = 0.0
    recording_enabled: bool = False
    ai_interaction: bool = False


@dataclass
class E2ECallResult:
    """Result of end-to-end call test."""
    scenario_id: str
    call_id: str
    start_time: float
    end_time: float
    total_duration: float
    setup_time_ms: float
    teardown_time_ms: float
    success: bool
    call_quality_mos: Optional[float] = None
    audio_packets_sent: int = 0
    audio_packets_received: int = 0
    dtmf_digits_sent: List[str] = field(default_factory=list)
    dtmf_digits_received: List[str] = field(default_factory=list)
    events_log: List[Dict[str, Any]] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    network_metrics: Dict[str, Any] = field(default_factory=dict)


class E2ECallTester:
    """End-to-end call testing framework."""
    
    def __init__(self, sip_server_host: str, sip_server_port: int = 5060,
                 api_base_url: str = "http://localhost:8000",
                 websocket_url: str = "ws://localhost:8080/ws"):
        self.sip_server_host = sip_server_host
        self.sip_server_port = sip_server_port
        self.api_base_url = api_base_url
        self.websocket_url = websocket_url
        
        self.logger = logging.getLogger(__name__)
        
        # Test results storage
        self.test_results: List[E2ECallResult] = []
        
        # HTTP session for API calls
        self.http_session = None
        
        # WebSocket connections for AI bridge testing
        self.websocket_connections = {}
        
        # Audio generator for RTP simulation
        self.audio_generator = AudioGenerator()
    
    async def initialize(self):
        """Initialize test framework."""
        self.logger.info("Initializing E2E call test framework")
        
        # Create HTTP session
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "E2E-Call-Tester/1.0"
        }
        
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=50,
            ttl_dns_cache=300
        )
        
        self.http_session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
    
    async def cleanup(self):
        """Cleanup test framework."""
        if self.http_session:
            await self.http_session.close()
        
        # Close any open WebSocket connections
        for ws in self.websocket_connections.values():
            if not ws.closed:
                await ws.close()
    
    def generate_call_id(self) -> str:
        """Generate unique call ID."""
        return f"e2e-call-{int(time.time())}-{random.randint(1000, 9999)}"
    
    def generate_via_branch(self) -> str:
        """Generate Via branch parameter."""
        return f"z9hG4bK{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}"
    
    def generate_tag(self) -> str:
        """Generate tag parameter."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def create_sip_invite(self, caller: CallParticipant, callee: CallParticipant,
                         call_id: str) -> str:
        """Create SIP INVITE message."""
        branch = self.generate_via_branch()
        from_tag = self.generate_tag()
        
        # Generate SDP
        sdp = self.create_sdp_offer(caller)
        content_length = len(sdp.encode('utf-8'))
        
        invite = f"""INVITE sip:{callee.number}@{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {caller.local_ip}:{caller.local_port};branch={branch}
Max-Forwards: 70
To: "{callee.name}" <sip:{callee.number}@{self.sip_server_host}>
From: "{caller.name}" <sip:{caller.number}@{self.sip_server_host}>;tag={from_tag}
Call-ID: {call_id}
CSeq: 1 INVITE
Contact: <sip:{caller.number}@{caller.local_ip}:{caller.local_port}>
Content-Type: application/sdp
Content-Length: {content_length}
User-Agent: {caller.user_agent}
Allow: INVITE, ACK, CANCEL, BYE, REFER, OPTIONS, MESSAGE
Supported: replaces

{sdp}"""
        
        return invite.replace('\n', '\r\n')
    
    def create_sdp_offer(self, participant: CallParticipant) -> str:
        """Create SDP offer for call."""
        session_id = int(time.time())
        
        sdp = f"""v=0
o=- {session_id} {session_id} IN IP4 {participant.local_ip}
s=E2E Call Test
c=IN IP4 {participant.local_ip}
t=0 0
m=audio 5004 RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv"""
        
        return sdp
    
    async def send_sip_request(self, sip_message: str, 
                             timeout: float = 10.0) -> Optional[str]:
        """Send SIP request and wait for response."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            
            # Send request
            sock.sendto(sip_message.encode(), (self.sip_server_host, self.sip_server_port))
            
            # Wait for response
            response_data, addr = sock.recvfrom(4096)
            response = response_data.decode()
            
            sock.close()
            return response
            
        except Exception as e:
            self.logger.error(f"SIP request failed: {e}")
            return None
    
    async def establish_websocket_connection(self, call_id: str) -> Optional[websockets.WebSocketServerProtocol]:
        """Establish WebSocket connection for AI bridge testing."""
        try:
            websocket = await websockets.connect(
                self.websocket_url,
                ping_interval=30,
                ping_timeout=10
            )
            
            # Send call start message
            call_start_message = {
                "type": "call_start",
                "data": {
                    "call_id": call_id,
                    "from_number": "+15551234567",
                    "to_number": "+15556789012",
                    "codec": "PCMU",
                    "sample_rate": 8000,
                    "timestamp": time.time()
                }
            }
            
            await websocket.send(json.dumps(call_start_message))
            
            # Wait for acknowledgment
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            
            self.websocket_connections[call_id] = websocket
            return websocket
            
        except Exception as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            return None
    
    async def simulate_audio_stream(self, call_id: str, duration: float,
                                  websocket: Optional[websockets.WebSocketServerProtocol] = None) -> Tuple[int, int]:
        """Simulate audio streaming for call duration."""
        audio_sent = 0
        audio_received = 0
        
        # Audio parameters
        frame_rate = 50  # 50fps (20ms frames)
        frame_interval = 1.0 / frame_rate
        
        start_time = time.time()
        end_time = start_time + duration
        
        while time.time() < end_time:
            frame_start = time.time()
            
            # Generate audio frame
            audio_frame = self.audio_generator.generate_pcmu_frame()
            audio_sent += 1
            
            # Send via WebSocket if available
            if websocket and not websocket.closed:
                try:
                    audio_message = {
                        "type": "audio_data",
                        "data": {
                            "call_id": call_id,
                            "audio": audio_frame.hex(),  # Convert to hex for JSON
                            "timestamp": time.time(),
                            "sequence": audio_sent
                        }
                    }
                    
                    await websocket.send(json.dumps(audio_message))
                    
                    # Try to receive audio (non-blocking)
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=0.001)
                        data = json.loads(response)
                        if data.get("type") == "audio_data":
                            audio_received += 1
                    except asyncio.TimeoutError:
                        pass  # No audio received, continue
                        
                except Exception as e:
                    self.logger.warning(f"Audio streaming error: {e}")
            
            # Control frame rate
            elapsed = time.time() - frame_start
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)
        
        return audio_sent, audio_received
    
    async def send_dtmf_sequence(self, call_id: str, digits: str,
                               websocket: Optional[websockets.WebSocketServerProtocol] = None) -> List[str]:
        """Send DTMF digit sequence."""
        sent_digits = []
        
        for digit in digits:
            if websocket and not websocket.closed:
                try:
                    dtmf_message = {
                        "type": "dtmf",
                        "data": {
                            "call_id": call_id,
                            "digit": digit,
                            "timestamp": time.time()
                        }
                    }
                    
                    await websocket.send(json.dumps(dtmf_message))
                    sent_digits.append(digit)
                    
                    # Wait between digits
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    self.logger.warning(f"DTMF sending error: {e}")
                    break
        
        return sent_digits
    
    async def simulate_call_hold(self, call_id: str, hold_duration: float) -> bool:
        """Simulate call hold and resume."""
        try:
            # Send hold request via API
            hold_data = {"call_id": call_id}
            
            async with self.http_session.post(
                f"{self.api_base_url}/api/calls/{call_id}/hold"
            ) as response:
                if response.status != 200:
                    return False
            
            # Wait for hold duration
            await asyncio.sleep(hold_duration)
            
            # Send resume request
            async with self.http_session.post(
                f"{self.api_base_url}/api/calls/{call_id}/resume"
            ) as response:
                return response.status == 200
                
        except Exception as e:
            self.logger.error(f"Call hold simulation failed: {e}")
            return False
    
    async def simulate_call_transfer(self, call_id: str, transfer_target: str) -> bool:
        """Simulate call transfer."""
        try:
            transfer_data = {
                "target_number": transfer_target,
                "blind_transfer": True
            }
            
            async with self.http_session.post(
                f"{self.api_base_url}/api/calls/{call_id}/transfer",
                json=transfer_data
            ) as response:
                return response.status == 200
                
        except Exception as e:
            self.logger.error(f"Call transfer simulation failed: {e}")
            return False
    
    async def run_call_scenario(self, scenario: CallScenario) -> E2ECallResult:
        """Run complete call scenario test."""
        self.logger.info(f"Running call scenario: {scenario.name}")
        
        call_id = self.generate_call_id()
        start_time = time.time()
        
        result = E2ECallResult(
            scenario_id=scenario.scenario_id,
            call_id=call_id,
            start_time=start_time,
            end_time=0,
            total_duration=0,
            setup_time_ms=0,
            teardown_time_ms=0,
            success=False
        )
        
        try:
            # Phase 1: Call Setup
            setup_start = time.time()
            
            # Create and send INVITE
            invite = self.create_sip_invite(scenario.caller, scenario.callee, call_id)
            response = await self.send_sip_request(invite)
            
            if not response or "200 OK" not in response:
                result.error_messages.append(f"INVITE failed: {response}")
                return result
            
            setup_end = time.time()
            result.setup_time_ms = (setup_end - setup_start) * 1000
            result.events_log.append({
                "timestamp": setup_end,
                "event": "call_setup_complete",
                "duration_ms": result.setup_time_ms
            })
            
            # Phase 2: WebSocket Connection (if AI interaction enabled)
            websocket = None
            if scenario.ai_interaction:
                websocket = await self.establish_websocket_connection(call_id)
                if websocket:
                    result.events_log.append({
                        "timestamp": time.time(),
                        "event": "websocket_connected"
                    })
            
            # Phase 3: Audio Streaming
            if scenario.include_audio:
                audio_start = time.time()
                
                # Simulate some audio before any special actions
                initial_audio_duration = min(5.0, scenario.duration_seconds / 3)
                audio_sent, audio_received = await self.simulate_audio_stream(
                    call_id, initial_audio_duration, websocket
                )
                
                result.audio_packets_sent += audio_sent
                result.audio_packets_received += audio_received
                
                remaining_duration = scenario.duration_seconds - initial_audio_duration
                
                # Phase 4: DTMF Testing
                if scenario.include_dtmf and scenario.dtmf_sequence:
                    dtmf_start = time.time()
                    sent_digits = await self.send_dtmf_sequence(
                        call_id, scenario.dtmf_sequence, websocket
                    )
                    result.dtmf_digits_sent = sent_digits
                    
                    dtmf_duration = time.time() - dtmf_start
                    remaining_duration -= dtmf_duration
                    
                    result.events_log.append({
                        "timestamp": time.time(),
                        "event": "dtmf_sent",
                        "digits": sent_digits
                    })
                
                # Phase 5: Call Hold Testing
                if scenario.hold_duration > 0:
                    hold_success = await self.simulate_call_hold(call_id, scenario.hold_duration)
                    remaining_duration -= scenario.hold_duration
                    
                    result.events_log.append({
                        "timestamp": time.time(),
                        "event": "call_hold_resume",
                        "success": hold_success
                    })
                
                # Phase 6: Call Transfer Testing
                if scenario.transfer_target:
                    transfer_success = await self.simulate_call_transfer(
                        call_id, scenario.transfer_target
                    )
                    
                    result.events_log.append({
                        "timestamp": time.time(),
                        "event": "call_transfer",
                        "target": scenario.transfer_target,
                        "success": transfer_success
                    })
                
                # Continue audio streaming for remaining duration
                if remaining_duration > 0:
                    audio_sent_2, audio_received_2 = await self.simulate_audio_stream(
                        call_id, remaining_duration, websocket
                    )
                    result.audio_packets_sent += audio_sent_2
                    result.audio_packets_received += audio_received_2
            
            # Phase 7: Call Teardown
            teardown_start = time.time()
            
            # Send BYE request
            bye_request = self.create_sip_bye(scenario.caller, scenario.callee, call_id)
            bye_response = await self.send_sip_request(bye_request)
            
            # Close WebSocket if open
            if websocket and not websocket.closed:
                call_end_message = {
                    "type": "call_end",
                    "data": {
                        "call_id": call_id,
                        "reason": "normal",
                        "timestamp": time.time()
                    }
                }
                await websocket.send(json.dumps(call_end_message))
                await websocket.close()
            
            teardown_end = time.time()
            result.teardown_time_ms = (teardown_end - teardown_start) * 1000
            
            # Calculate final metrics
            result.end_time = teardown_end
            result.total_duration = result.end_time - result.start_time
            result.success = True
            
            # Calculate call quality score (simplified)
            if result.audio_packets_sent > 0:
                packet_loss_rate = 1 - (result.audio_packets_received / result.audio_packets_sent)
                result.call_quality_mos = max(1.0, 5.0 - (packet_loss_rate * 4.0))
            
            result.events_log.append({
                "timestamp": teardown_end,
                "event": "call_completed",
                "total_duration": result.total_duration
            })
            
        except Exception as e:
            result.error_messages.append(f"Call scenario failed: {str(e)}")
            result.end_time = time.time()
            result.total_duration = result.end_time - result.start_time
            self.logger.error(f"Call scenario {scenario.name} failed: {e}")
        
        self.test_results.append(result)
        return result
    
    def create_sip_bye(self, caller: CallParticipant, callee: CallParticipant,
                      call_id: str) -> str:
        """Create SIP BYE message."""
        branch = self.generate_via_branch()
        
        bye = f"""BYE sip:{callee.number}@{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {caller.local_ip}:{caller.local_port};branch={branch}
Max-Forwards: 70
To: "{callee.name}" <sip:{callee.number}@{self.sip_server_host}>
From: "{caller.name}" <sip:{caller.number}@{self.sip_server_host}>;tag=bye-tag
Call-ID: {call_id}
CSeq: 2 BYE
Contact: <sip:{caller.number}@{caller.local_ip}:{caller.local_port}>
Content-Length: 0
User-Agent: {caller.user_agent}"""
        
        return bye.replace('\n', '\r\n')
    
    def create_test_scenarios(self) -> List[CallScenario]:
        """Create predefined test scenarios."""
        scenarios = []
        
        # Basic call scenario
        scenarios.append(CallScenario(
            scenario_id="basic_call",
            name="Basic Voice Call",
            description="Simple voice call between two participants",
            caller=CallParticipant("+15551234567", "Alice"),
            callee=CallParticipant("+15556789012", "Bob"),
            duration_seconds=30.0,
            include_audio=True
        ))
        
        # DTMF testing scenario
        scenarios.append(CallScenario(
            scenario_id="dtmf_call",
            name="DTMF Testing Call",
            description="Call with DTMF digit transmission",
            caller=CallParticipant("+15551234568", "Charlie"),
            callee=CallParticipant("+15556789013", "Dave"),
            duration_seconds=45.0,
            include_audio=True,
            include_dtmf=True,
            dtmf_sequence="12345*#0"
        ))
        
        # Call hold scenario
        scenarios.append(CallScenario(
            scenario_id="hold_call",
            name="Call Hold and Resume",
            description="Call with hold and resume functionality",
            caller=CallParticipant("+15551234569", "Eve"),
            callee=CallParticipant("+15556789014", "Frank"),
            duration_seconds=60.0,
            include_audio=True,
            hold_duration=10.0
        ))
        
        # Call transfer scenario
        scenarios.append(CallScenario(
            scenario_id="transfer_call",
            name="Call Transfer",
            description="Call with transfer to another number",
            caller=CallParticipant("+15551234570", "Grace"),
            callee=CallParticipant("+15556789015", "Henry"),
            duration_seconds=40.0,
            include_audio=True,
            transfer_target="+15551111111"
        ))
        
        # AI interaction scenario
        scenarios.append(CallScenario(
            scenario_id="ai_call",
            name="AI Platform Integration",
            description="Call with AI platform WebSocket integration",
            caller=CallParticipant("+15551234571", "Iris"),
            callee=CallParticipant("+15556789016", "Jack"),
            duration_seconds=60.0,
            include_audio=True,
            include_dtmf=True,
            dtmf_sequence="123",
            ai_interaction=True
        ))
        
        # Long duration call
        scenarios.append(CallScenario(
            scenario_id="long_call",
            name="Extended Duration Call",
            description="Long duration call for stability testing",
            caller=CallParticipant("+15551234572", "Kate"),
            callee=CallParticipant("+15556789017", "Liam"),
            duration_seconds=300.0,  # 5 minutes
            include_audio=True
        ))
        
        return scenarios
    
    async def run_concurrent_scenarios(self, scenarios: List[CallScenario]) -> List[E2ECallResult]:
        """Run multiple call scenarios concurrently."""
        self.logger.info(f"Running {len(scenarios)} concurrent call scenarios")
        
        # Create tasks for concurrent execution
        tasks = [self.run_call_scenario(scenario) for scenario in scenarios]
        
        # Execute all scenarios concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, E2ECallResult):
                valid_results.append(result)
            else:
                self.logger.error(f"Scenario {scenarios[i].name} failed: {result}")
        
        return valid_results
    
    def analyze_results(self, results: List[E2ECallResult], test_name: str):
        """Analyze and print test results."""
        if not results:
            print(f"\nNo results for {test_name}")
            return
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        print(f"\n{'='*70}")
        print(f"📞 End-to-End Call Test: {test_name}")
        print(f"{'='*70}")
        print(f"Total Scenarios:     {len(results):,}")
        print(f"Successful:          {len(successful):,} ({len(successful)/len(results)*100:.2f}%)")
        print(f"Failed:              {len(failed):,}")
        
        if successful:
            # Setup time analysis
            setup_times = [r.setup_time_ms for r in successful]
            avg_setup = sum(setup_times) / len(setup_times)
            
            # Duration analysis
            durations = [r.total_duration for r in successful]
            avg_duration = sum(durations) / len(durations)
            
            # Audio analysis
            total_audio_sent = sum(r.audio_packets_sent for r in successful)
            total_audio_received = sum(r.audio_packets_received for r in successful)
            
            print(f"\n📊 Performance Metrics:")
            print(f"  Avg Setup Time:     {avg_setup:.2f}ms")
            print(f"  Avg Call Duration:  {avg_duration:.2f}s")
            print(f"  Audio Packets Sent: {total_audio_sent:,}")
            print(f"  Audio Packets Recv: {total_audio_received:,}")
            
            if total_audio_sent > 0:
                audio_success_rate = total_audio_received / total_audio_sent * 100
                print(f"  Audio Success Rate: {audio_success_rate:.2f}%")
            
            # Call quality analysis
            quality_scores = [r.call_quality_mos for r in successful if r.call_quality_mos]
            if quality_scores:
                avg_quality = sum(quality_scores) / len(quality_scores)
                print(f"  Avg Call Quality:   {avg_quality:.2f} MOS")
        
        # DTMF analysis
        dtmf_scenarios = [r for r in successful if r.dtmf_digits_sent]
        if dtmf_scenarios:
            total_dtmf_sent = sum(len(r.dtmf_digits_sent) for r in dtmf_scenarios)
            print(f"\n📱 DTMF Analysis:")
            print(f"  DTMF Scenarios:     {len(dtmf_scenarios)}")
            print(f"  Total Digits Sent:  {total_dtmf_sent}")
        
        # Error analysis
        if failed:
            error_counts = {}
            for result in failed:
                for error in result.error_messages:
                    error_key = error[:50]  # Truncate long errors
                    error_counts[error_key] = error_counts.get(error_key, 0) + 1
            
            print(f"\n❌ Error Analysis:")
            for error, count in error_counts.items():
                print(f"  {error}: {count}")
    
    def generate_detailed_report(self, output_file: str = "e2e_call_test_report.html"):
        """Generate detailed HTML report."""
        if not self.test_results:
            self.logger.warning("No test results to report")
            return
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>End-to-End Call Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #2196F3; color: white; padding: 20px; border-radius: 5px; }}
                .summary {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .scenario {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .success {{ border-left: 4px solid #4CAF50; }}
                .failed {{ border-left: 4px solid #f44336; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
                .metric {{ background: white; padding: 10px; border-left: 4px solid #2196F3; }}
                .events {{ max-height: 200px; overflow-y: auto; background: #f9f9f9; padding: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📞 End-to-End Call Test Report</h1>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Total Scenarios: {len(self.test_results)}</p>
            </div>
        """
        
        # Overall summary
        successful = [r for r in self.test_results if r.success]
        failed = [r for r in self.test_results if not r.success]
        
        html_content += f"""
        <div class="summary">
            <h2>📊 Test Summary</h2>
            <div class="metrics">
                <div class="metric">
                    <h4>Success Rate</h4>
                    <p>{len(successful)/len(self.test_results)*100:.1f}%</p>
                    <small>{len(successful)} of {len(self.test_results)} scenarios</small>
                </div>
        """
        
        if successful:
            avg_setup = sum(r.setup_time_ms for r in successful) / len(successful)
            total_audio = sum(r.audio_packets_sent for r in successful)
            
            html_content += f"""
                <div class="metric">
                    <h4>Avg Setup Time</h4>
                    <p>{avg_setup:.2f}ms</p>
                </div>
                <div class="metric">
                    <h4>Total Audio Packets</h4>
                    <p>{total_audio:,}</p>
                </div>
            """
        
        html_content += """
            </div>
        </div>
        
        <h2>📋 Scenario Results</h2>
        """
        
        # Individual scenario results
        for result in self.test_results:
            status_class = "success" if result.success else "failed"
            status_text = "✅ Success" if result.success else "❌ Failed"
            
            html_content += f"""
            <div class="scenario {status_class}">
                <h3>{result.scenario_id} - {status_text}</h3>
                <div class="metrics">
                    <div class="metric">
                        <h4>Duration</h4>
                        <p>{result.total_duration:.2f}s</p>
                    </div>
                    <div class="metric">
                        <h4>Setup Time</h4>
                        <p>{result.setup_time_ms:.2f}ms</p>
                    </div>
                    <div class="metric">
                        <h4>Audio Packets</h4>
                        <p>Sent: {result.audio_packets_sent}</p>
                        <p>Received: {result.audio_packets_received}</p>
                    </div>
            """
            
            if result.call_quality_mos:
                html_content += f"""
                    <div class="metric">
                        <h4>Call Quality</h4>
                        <p>{result.call_quality_mos:.2f} MOS</p>
                    </div>
                """
            
            html_content += "</div>"
            
            # Events log
            if result.events_log:
                html_content += """
                <h4>Events Log</h4>
                <div class="events">
                """
                for event in result.events_log:
                    timestamp = datetime.fromtimestamp(event['timestamp']).strftime('%H:%M:%S.%f')[:-3]
                    html_content += f"<p>{timestamp}: {event['event']}</p>"
                html_content += "</div>"
            
            # Errors
            if result.error_messages:
                html_content += "<h4>Errors</h4><ul>"
                for error in result.error_messages:
                    html_content += f"<li>{error}</li>"
                html_content += "</ul>"
            
            html_content += "</div>"
        
        html_content += """
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        self.logger.info(f"Detailed report generated: {output_file}")


class AudioGenerator:
    """Generate audio frames for testing."""
    
    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        self.frame_size = 160  # 20ms at 8kHz
        self.sequence = 0
    
    def generate_pcmu_frame(self) -> bytes:
        """Generate PCMU audio frame."""
        # Generate simple sine wave
        import math
        frequency = 440  # 440 Hz tone
        
        samples = []
        for i in range(self.frame_size):
            sample_index = self.sequence * self.frame_size + i
            sample = int(16384 * math.sin(2 * math.pi * frequency * sample_index / self.sample_rate))
            
            # Convert to μ-law (simplified)
            if sample >= 0:
                compressed = min(127, sample // 256)
            else:
                compressed = max(-128, sample // 256)
            
            samples.append(compressed & 0xFF)
        
        self.sequence += 1
        return bytes(samples)


async def main():
    """Main function for end-to-end call testing."""
    parser = argparse.ArgumentParser(description="End-to-End Call Testing")
    parser.add_argument("--host", default="localhost", help="SIP server host")
    parser.add_argument("--port", type=int, default=5060, help="SIP server port")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--websocket-url", default="ws://localhost:8080/ws", help="WebSocket URL")
    parser.add_argument("--test",
                       choices=["basic", "dtmf", "hold", "transfer", "ai", "long", "concurrent", "all"],
                       default="all",
                       help="Test type to run")
    parser.add_argument("--output", default="e2e_call_test_report.html",
                       help="Output report file")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print("📞 End-to-End Call Testing Suite")
    print(f"SIP Server: {args.host}:{args.port}")
    print(f"API URL: {args.api_url}")
    print(f"WebSocket: {args.websocket_url}")
    print(f"Test: {args.test}")
    print("=" * 60)
    
    tester = E2ECallTester(args.host, args.port, args.api_url, args.websocket_url)
    
    try:
        await tester.initialize()
        
        scenarios = tester.create_test_scenarios()
        
        if args.test == "all":
            # Run all scenarios
            results = await tester.run_concurrent_scenarios(scenarios)
            tester.analyze_results(results, "Complete E2E Test Suite")
            
        elif args.test == "concurrent":
            # Run basic scenarios concurrently
            basic_scenarios = [s for s in scenarios if s.scenario_id in ["basic_call", "dtmf_call"]]
            results = await tester.run_concurrent_scenarios(basic_scenarios * 3)  # Run 3 instances each
            tester.analyze_results(results, "Concurrent Call Tests")
            
        else:
            # Run specific test
            scenario_map = {s.scenario_id: s for s in scenarios}
            scenario_key = f"{args.test}_call"
            
            if scenario_key in scenario_map:
                result = await tester.run_call_scenario(scenario_map[scenario_key])
                tester.analyze_results([result], f"{args.test.title()} Call Test")
            else:
                print(f"Unknown test type: {args.test}")
        
        # Generate detailed report
        tester.generate_detailed_report(args.output)
        print(f"\n📋 Detailed report generated: {args.output}")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
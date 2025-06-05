"""WebSocket bridge load testing for AI platform integration."""
import asyncio
import websockets
import json
import time
import base64
import random
import logging
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import statistics
import uuid


@dataclass
class WebSocketTestResult:
    """Result of WebSocket test."""
    connection_id: str
    start_time: float
    end_time: float
    duration: float
    messages_sent: int
    messages_received: int
    audio_frames_sent: int
    audio_frames_received: int
    success: bool
    error: Optional[str] = None
    latency_measurements: List[float] = None


class WebSocketBridgeLoadTester:
    """Load tester for WebSocket bridge functionality."""
    
    def __init__(self, websocket_url: str):
        self.websocket_url = websocket_url
        self.results: List[WebSocketTestResult] = []
        self.logger = logging.getLogger(__name__)
        
    def generate_call_id(self) -> str:
        """Generate unique call ID."""
        return str(uuid.uuid4())
    
    def generate_audio_frame(self, frame_size: int = 320) -> bytes:
        """Generate fake PCM audio frame (16-bit, 8kHz, 20ms)."""
        # Generate sine wave for testing
        import math
        samples = []
        for i in range(frame_size // 2):  # 16-bit samples
            # Generate 440Hz sine wave
            sample = int(16384 * math.sin(2 * math.pi * 440 * i / 8000))
            # Convert to signed 16-bit little-endian
            samples.extend([sample & 0xFF, (sample >> 8) & 0xFF])
        return bytes(samples)
    
    def create_call_start_message(self, call_id: str, from_number: str, to_number: str) -> str:
        """Create call start message."""
        message = {
            "type": "call_start",
            "data": {
                "call_id": call_id,
                "from_number": from_number,
                "to_number": to_number,
                "codec": "PCMU",
                "sample_rate": 8000,
                "timestamp": time.time()
            }
        }
        return json.dumps(message)
    
    def create_audio_message(self, call_id: str, audio_data: bytes) -> str:
        """Create audio data message."""
        message = {
            "type": "audio_data",
            "data": {
                "call_id": call_id,
                "audio": base64.b64encode(audio_data).decode(),
                "timestamp": time.time(),
                "sequence": random.randint(1, 65535)
            }
        }
        return json.dumps(message)
    
    def create_dtmf_message(self, call_id: str, digit: str) -> str:
        """Create DTMF message."""
        message = {
            "type": "dtmf",
            "data": {
                "call_id": call_id,
                "digit": digit,
                "timestamp": time.time()
            }
        }
        return json.dumps(message)
    
    def create_call_end_message(self, call_id: str) -> str:
        """Create call end message."""
        message = {
            "type": "call_end",
            "data": {
                "call_id": call_id,
                "reason": "normal",
                "timestamp": time.time()
            }
        }
        return json.dumps(message)
    
    def create_heartbeat_message(self) -> str:
        """Create heartbeat message."""
        message = {
            "type": "heartbeat",
            "timestamp": time.time()
        }
        return json.dumps(message)
    
    async def single_connection_test(self, connection_id: str, duration: int, 
                                   audio_rate: int = 50) -> WebSocketTestResult:
        """Test single WebSocket connection with audio streaming."""
        start_time = time.time()
        messages_sent = 0
        messages_received = 0
        audio_frames_sent = 0
        audio_frames_received = 0
        latency_measurements = []
        
        try:
            async with websockets.connect(
                self.websocket_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            ) as websocket:
                
                call_id = self.generate_call_id()
                
                # Send call start
                call_start = self.create_call_start_message(
                    call_id, 
                    f"+1555{connection_id[-6:]}",
                    "+15551234567"
                )
                await websocket.send(call_start)
                messages_sent += 1
                
                # Wait for acknowledgment
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    messages_received += 1
                except asyncio.TimeoutError:
                    pass
                
                # Audio streaming phase
                audio_interval = 1.0 / audio_rate  # 20ms for 50fps
                end_time = start_time + duration
                
                async def send_audio():
                    """Send audio frames."""
                    nonlocal audio_frames_sent, messages_sent
                    
                    while time.time() < end_time:
                        frame_start = time.time()
                        
                        # Generate and send audio frame
                        audio_data = self.generate_audio_frame()
                        audio_message = self.create_audio_message(call_id, audio_data)
                        
                        await websocket.send(audio_message)
                        audio_frames_sent += 1
                        messages_sent += 1
                        
                        # Occasionally send DTMF
                        if audio_frames_sent % 100 == 0:
                            digit = random.choice("0123456789*#")
                            dtmf_message = self.create_dtmf_message(call_id, digit)
                            await websocket.send(dtmf_message)
                            messages_sent += 1
                        
                        # Control frame rate
                        elapsed = time.time() - frame_start
                        if elapsed < audio_interval:
                            await asyncio.sleep(audio_interval - elapsed)
                
                async def receive_messages():
                    """Receive and process messages."""
                    nonlocal messages_received, audio_frames_received, latency_measurements
                    
                    while time.time() < end_time:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            messages_received += 1
                            
                            # Parse message for latency measurement
                            try:
                                data = json.loads(message)
                                if data.get("type") == "audio_data":
                                    audio_frames_received += 1
                                    
                                    # Calculate latency if timestamp available
                                    if "timestamp" in data.get("data", {}):
                                        sent_time = data["data"]["timestamp"]
                                        latency = time.time() - sent_time
                                        latency_measurements.append(latency)
                                        
                            except json.JSONDecodeError:
                                pass
                                
                        except asyncio.TimeoutError:
                            # Send heartbeat
                            heartbeat = self.create_heartbeat_message()
                            await websocket.send(heartbeat)
                            messages_sent += 1
                
                # Run send and receive concurrently
                await asyncio.gather(
                    send_audio(),
                    receive_messages()
                )
                
                # Send call end
                call_end = self.create_call_end_message(call_id)
                await websocket.send(call_end)
                messages_sent += 1
                
                # Wait for final response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    messages_received += 1
                except asyncio.TimeoutError:
                    pass
                
                final_time = time.time()
                
                result = WebSocketTestResult(
                    connection_id=connection_id,
                    start_time=start_time,
                    end_time=final_time,
                    duration=final_time - start_time,
                    messages_sent=messages_sent,
                    messages_received=messages_received,
                    audio_frames_sent=audio_frames_sent,
                    audio_frames_received=audio_frames_received,
                    success=True,
                    latency_measurements=latency_measurements
                )
                
        except Exception as e:
            final_time = time.time()
            result = WebSocketTestResult(
                connection_id=connection_id,
                start_time=start_time,
                end_time=final_time,
                duration=final_time - start_time,
                messages_sent=messages_sent,
                messages_received=messages_received,
                audio_frames_sent=audio_frames_sent,
                audio_frames_received=audio_frames_received,
                success=False,
                error=str(e),
                latency_measurements=latency_measurements
            )
        
        self.results.append(result)
        return result
    
    async def concurrent_connections_test(self, num_connections: int, duration: int, 
                                        audio_rate: int = 50) -> List[WebSocketTestResult]:
        """Test multiple concurrent WebSocket connections."""
        self.logger.info(f"Starting {num_connections} concurrent WebSocket connections for {duration}s")
        
        tasks = []
        for i in range(num_connections):
            connection_id = f"conn-{i:04d}"
            task = self.single_connection_test(connection_id, duration, audio_rate)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, WebSocketTestResult)]
        return valid_results
    
    async def ramp_up_connections_test(self, max_connections: int, ramp_duration: int, 
                                     test_duration: int) -> List[WebSocketTestResult]:
        """Gradually ramp up WebSocket connections."""
        self.logger.info(f"Ramping up to {max_connections} connections over {ramp_duration}s")
        
        results = []
        connections_per_second = max_connections / ramp_duration
        
        async def start_connection_batch(batch_id: int, delay: float):
            """Start a batch of connections after delay."""
            await asyncio.sleep(delay)
            
            batch_size = max(1, int(connections_per_second))
            tasks = []
            
            for i in range(batch_size):
                connection_id = f"ramp-{batch_id:03d}-{i:02d}"
                task = self.single_connection_test(connection_id, test_duration)
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in batch_results if isinstance(r, WebSocketTestResult)]
        
        # Create batches
        batch_tasks = []
        for batch_id in range(ramp_duration):
            delay = batch_id  # 1 second intervals
            task = start_connection_batch(batch_id, delay)
            batch_tasks.append(task)
        
        # Wait for all batches to complete
        batch_results = await asyncio.gather(*batch_tasks)
        
        # Flatten results
        for batch in batch_results:
            results.extend(batch)
        
        return results
    
    async def stress_test_connections(self, target_connections: int, duration: int) -> List[WebSocketTestResult]:
        """Stress test with high connection count."""
        self.logger.info(f"Stress testing with {target_connections} connections")
        
        # Start connections in waves to avoid overwhelming the server
        wave_size = min(50, target_connections // 10)  # 10 waves max
        waves = []
        
        for wave_start in range(0, target_connections, wave_size):
            wave_end = min(wave_start + wave_size, target_connections)
            wave_connections = wave_end - wave_start
            
            wave_tasks = []
            for i in range(wave_connections):
                connection_id = f"stress-{wave_start + i:04d}"
                task = self.single_connection_test(connection_id, duration, audio_rate=25)
                wave_tasks.append(task)
            
            waves.append(wave_tasks)
        
        # Start waves with small delays
        all_tasks = []
        for i, wave in enumerate(waves):
            await asyncio.sleep(1)  # 1 second between waves
            all_tasks.extend(wave)
        
        # Wait for all connections to complete
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        valid_results = [r for r in results if isinstance(r, WebSocketTestResult)]
        
        return valid_results
    
    def analyze_results(self, results: List[WebSocketTestResult], test_name: str):
        """Analyze WebSocket test results."""
        if not results:
            print(f"No results for {test_name}")
            return
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        # Connection metrics
        total_duration = sum(r.duration for r in successful)
        total_messages_sent = sum(r.messages_sent for r in successful)
        total_messages_received = sum(r.messages_received for r in successful)
        total_audio_frames_sent = sum(r.audio_frames_sent for r in successful)
        total_audio_frames_received = sum(r.audio_frames_received for r in successful)
        
        # Latency metrics
        all_latencies = []
        for r in successful:
            if r.latency_measurements:
                all_latencies.extend(r.latency_measurements)
        
        print(f"\n{'='*70}")
        print(f"🌐 WebSocket Bridge Load Test: {test_name}")
        print(f"{'='*70}")
        print(f"Total Connections:      {len(results):,}")
        print(f"Successful:             {len(successful):,} ({len(successful)/len(results)*100:.2f}%)")
        print(f"Failed:                 {len(failed):,}")
        
        if successful:
            avg_duration = statistics.mean(r.duration for r in successful)
            print(f"\n📊 Connection Metrics:")
            print(f"  Avg Duration:         {avg_duration:.2f}s")
            print(f"  Total Messages Sent:  {total_messages_sent:,}")
            print(f"  Total Messages Recv:  {total_messages_received:,}")
            print(f"  Message Success Rate: {total_messages_received/total_messages_sent*100:.2f}%")
            
            print(f"\n🎵 Audio Streaming:")
            print(f"  Audio Frames Sent:    {total_audio_frames_sent:,}")
            print(f"  Audio Frames Recv:    {total_audio_frames_received:,}")
            if total_audio_frames_sent > 0:
                audio_success_rate = total_audio_frames_received / total_audio_frames_sent * 100
                print(f"  Audio Success Rate:   {audio_success_rate:.2f}%")
                
                # Calculate effective bitrate
                frame_size = 320  # bytes per frame
                avg_fps = total_audio_frames_sent / total_duration * len(successful)
                effective_bitrate = avg_fps * frame_size * 8 / 1000  # kbps
                print(f"  Avg Audio FPS:        {avg_fps:.1f}")
                print(f"  Effective Bitrate:    {effective_bitrate:.1f} kbps")
        
        if all_latencies:
            print(f"\n⏱️  Latency Metrics:")
            print(f"  Samples:              {len(all_latencies):,}")
            print(f"  Average:              {statistics.mean(all_latencies)*1000:.2f}ms")
            print(f"  Median:               {statistics.median(all_latencies)*1000:.2f}ms")
            print(f"  Min:                  {min(all_latencies)*1000:.2f}ms")
            print(f"  Max:                  {max(all_latencies)*1000:.2f}ms")
            
            # Percentiles
            import numpy as np
            p95 = np.percentile(all_latencies, 95) * 1000
            p99 = np.percentile(all_latencies, 99) * 1000
            print(f"  95th percentile:      {p95:.2f}ms")
            print(f"  99th percentile:      {p99:.2f}ms")
        
        # Error breakdown
        if failed:
            error_counts = {}
            for r in failed:
                error_key = r.error or "Unknown error"
                error_counts[error_key] = error_counts.get(error_key, 0) + 1
            
            print(f"\n❌ Error Breakdown:")
            for error, count in error_counts.items():
                print(f"  {error}: {count}")


async def main():
    """Main function for WebSocket bridge load testing."""
    parser = argparse.ArgumentParser(description="WebSocket Bridge Load Testing")
    parser.add_argument("--url", default="ws://localhost:8080/ws", 
                       help="WebSocket URL")
    parser.add_argument("--test",
                       choices=["single", "concurrent", "ramp", "stress"],
                       default="concurrent",
                       help="Test type")
    parser.add_argument("--connections", type=int, default=10,
                       help="Number of concurrent connections")
    parser.add_argument("--duration", type=int, default=30,
                       help="Test duration in seconds")
    parser.add_argument("--audio-rate", type=int, default=50,
                       help="Audio frames per second")
    parser.add_argument("--ramp-duration", type=int, default=30,
                       help="Ramp-up duration for ramp test")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print(f"🚀 WebSocket Bridge Load Testing")
    print(f"Target: {args.url}")
    print(f"Test: {args.test}")
    print(f"Connections: {args.connections}")
    print(f"Duration: {args.duration}s")
    print("=" * 60)
    
    tester = WebSocketBridgeLoadTester(args.url)
    
    try:
        if args.test == "single":
            result = await tester.single_connection_test("single-test", args.duration, args.audio_rate)
            tester.analyze_results([result], "Single Connection Test")
            
        elif args.test == "concurrent":
            results = await tester.concurrent_connections_test(
                args.connections, args.duration, args.audio_rate
            )
            tester.analyze_results(results, f"Concurrent Connections Test ({args.connections})")
            
        elif args.test == "ramp":
            results = await tester.ramp_up_connections_test(
                args.connections, args.ramp_duration, args.duration
            )
            tester.analyze_results(results, f"Ramp-up Test (0 -> {args.connections})")
            
        elif args.test == "stress":
            results = await tester.stress_test_connections(args.connections, args.duration)
            tester.analyze_results(results, f"Stress Test ({args.connections} connections)")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
"""SIP protocol-specific load testing using raw SIP messages."""
import asyncio
import socket
import time
import random
import string
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import argparse
from concurrent.futures import ThreadPoolExecutor
import threading


@dataclass
class SIPTestResult:
    """Result of a SIP protocol test."""
    start_time: float
    end_time: float
    response_time: float
    request_type: str
    response_code: Optional[int]
    success: bool
    error: Optional[str] = None


class SIPProtocolTester:
    """Load tester for SIP protocol using raw UDP sockets."""
    
    def __init__(self, sip_server_host: str, sip_server_port: int = 5060):
        self.sip_server_host = sip_server_host
        self.sip_server_port = sip_server_port
        self.results: List[SIPTestResult] = []
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Local endpoint for testing
        self.local_host = "127.0.0.1"
        self.local_port = 5080
        
    def generate_call_id(self) -> str:
        """Generate unique Call-ID."""
        return f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}@loadtest"
    
    def generate_via_branch(self) -> str:
        """Generate Via branch parameter."""
        return f"z9hG4bK{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}"
    
    def generate_tag(self) -> str:
        """Generate tag parameter."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def create_sip_invite(self, from_number: str, to_number: str) -> str:
        """Create SIP INVITE message."""
        call_id = self.generate_call_id()
        branch = self.generate_via_branch()
        from_tag = self.generate_tag()
        
        invite = f"""INVITE sip:{to_number}@{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {self.local_host}:{self.local_port};branch={branch}
Max-Forwards: 70
To: <sip:{to_number}@{self.sip_server_host}>
From: <sip:{from_number}@{self.sip_server_host}>;tag={from_tag}
Call-ID: {call_id}
CSeq: 1 INVITE
Contact: <sip:{from_number}@{self.local_host}:{self.local_port}>
Content-Type: application/sdp
Content-Length: 299
User-Agent: SIP-LoadTester/1.0

v=0
o=- {int(time.time())} {int(time.time())} IN IP4 {self.local_host}
s=Load Test Session
c=IN IP4 {self.local_host}
t=0 0
m=audio 5004 RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv"""
        
        return invite.replace('\n', '\r\n') + '\r\n'
    
    def create_sip_register(self, username: str) -> str:
        """Create SIP REGISTER message."""
        call_id = self.generate_call_id()
        branch = self.generate_via_branch()
        
        register = f"""REGISTER sip:{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {self.local_host}:{self.local_port};branch={branch}
Max-Forwards: 70
To: <sip:{username}@{self.sip_server_host}>
From: <sip:{username}@{self.sip_server_host}>;tag={self.generate_tag()}
Call-ID: {call_id}
CSeq: 1 REGISTER
Contact: <sip:{username}@{self.local_host}:{self.local_port}>
Content-Length: 0
User-Agent: SIP-LoadTester/1.0
Expires: 3600"""
        
        return register.replace('\n', '\r\n') + '\r\n'
    
    def create_sip_options(self) -> str:
        """Create SIP OPTIONS message for keepalive."""
        call_id = self.generate_call_id()
        branch = self.generate_via_branch()
        
        options = f"""OPTIONS sip:{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {self.local_host}:{self.local_port};branch={branch}
Max-Forwards: 70
To: <sip:{self.sip_server_host}>
From: <sip:loadtest@{self.sip_server_host}>;tag={self.generate_tag()}
Call-ID: {call_id}
CSeq: 1 OPTIONS
Content-Length: 0
User-Agent: SIP-LoadTester/1.0"""
        
        return options.replace('\n', '\r\n') + '\r\n'
    
    def create_sip_message(self, from_number: str, to_number: str, message_body: str) -> str:
        """Create SIP MESSAGE for SMS testing."""
        call_id = self.generate_call_id()
        branch = self.generate_via_branch()
        
        sip_message = f"""MESSAGE sip:{to_number}@{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {self.local_host}:{self.local_port};branch={branch}
Max-Forwards: 70
To: <sip:{to_number}@{self.sip_server_host}>
From: <sip:{from_number}@{self.sip_server_host}>;tag={self.generate_tag()}
Call-ID: {call_id}
CSeq: 1 MESSAGE
Contact: <sip:{from_number}@{self.local_host}:{self.local_port}>
Content-Type: text/plain
Content-Length: {len(message_body)}
User-Agent: SIP-LoadTester/1.0

{message_body}"""
        
        return sip_message.replace('\n', '\r\n') + '\r\n'
    
    def parse_sip_response(self, response: str) -> Optional[int]:
        """Parse SIP response and extract status code."""
        try:
            lines = response.split('\r\n')
            if lines and lines[0].startswith('SIP/2.0'):
                status_line = lines[0].split()
                if len(status_line) >= 2:
                    return int(status_line[1])
        except (ValueError, IndexError):
            pass
        return None
    
    async def send_sip_request(self, message: str, request_type: str, timeout: float = 5.0) -> SIPTestResult:
        """Send SIP request and measure response time."""
        start_time = time.time()
        
        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            
            # Send request
            sock.sendto(message.encode(), (self.sip_server_host, self.sip_server_port))
            
            # Wait for response
            try:
                response_data, addr = sock.recvfrom(4096)
                response = response_data.decode()
                response_code = self.parse_sip_response(response)
                
                end_time = time.time()
                
                # Consider 2xx, 3xx responses as success for load testing
                success = response_code is not None and 200 <= response_code < 400
                
                result = SIPTestResult(
                    start_time=start_time,
                    end_time=end_time,
                    response_time=end_time - start_time,
                    request_type=request_type,
                    response_code=response_code,
                    success=success
                )
                
            except socket.timeout:
                end_time = time.time()
                result = SIPTestResult(
                    start_time=start_time,
                    end_time=end_time,
                    response_time=end_time - start_time,
                    request_type=request_type,
                    response_code=None,
                    success=False,
                    error="Timeout"
                )
            
            sock.close()
            self.results.append(result)
            return result
            
        except Exception as e:
            end_time = time.time()
            result = SIPTestResult(
                start_time=start_time,
                end_time=end_time,
                response_time=end_time - start_time,
                request_type=request_type,
                response_code=None,
                success=False,
                error=str(e)
            )
            self.results.append(result)
            return result
    
    async def load_test_invite(self, num_calls: int, calls_per_second: int = 10) -> List[SIPTestResult]:
        """Load test INVITE requests."""
        self.logger.info(f"Starting INVITE load test: {num_calls} calls at {calls_per_second} CPS")
        
        results = []
        call_interval = 1.0 / calls_per_second
        
        for i in range(num_calls):
            from_number = f"+1555{i:07d}"
            to_number = f"+1556{i:07d}"
            
            invite_message = self.create_sip_invite(from_number, to_number)
            
            # Send INVITE
            task = self.send_sip_request(invite_message, "INVITE")
            result = await task
            results.append(result)
            
            # Control call rate
            if i < num_calls - 1:
                await asyncio.sleep(call_interval)
        
        return results
    
    async def load_test_register(self, num_registrations: int, rate: int = 5) -> List[SIPTestResult]:
        """Load test REGISTER requests."""
        self.logger.info(f"Starting REGISTER load test: {num_registrations} registrations")
        
        results = []
        interval = 1.0 / rate
        
        for i in range(num_registrations):
            username = f"user{i:06d}"
            register_message = self.create_sip_register(username)
            
            task = self.send_sip_request(register_message, "REGISTER")
            result = await task
            results.append(result)
            
            if i < num_registrations - 1:
                await asyncio.sleep(interval)
        
        return results
    
    async def load_test_options(self, num_requests: int, rate: int = 20) -> List[SIPTestResult]:
        """Load test OPTIONS requests."""
        self.logger.info(f"Starting OPTIONS load test: {num_requests} requests")
        
        results = []
        interval = 1.0 / rate
        
        for i in range(num_requests):
            options_message = self.create_sip_options()
            
            task = self.send_sip_request(options_message, "OPTIONS")
            result = await task
            results.append(result)
            
            if i < num_requests - 1:
                await asyncio.sleep(interval)
        
        return results
    
    async def load_test_message(self, num_messages: int, rate: int = 10) -> List[SIPTestResult]:
        """Load test SIP MESSAGE requests."""
        self.logger.info(f"Starting MESSAGE load test: {num_messages} messages")
        
        results = []
        interval = 1.0 / rate
        
        for i in range(num_messages):
            from_number = f"+1555{i:07d}"
            to_number = f"+1556{i:07d}"
            message_body = f"Load test SMS message {i}"
            
            sip_message = self.create_sip_message(from_number, to_number, message_body)
            
            task = self.send_sip_request(sip_message, "MESSAGE")
            result = await task
            results.append(result)
            
            if i < num_messages - 1:
                await asyncio.sleep(interval)
        
        return results
    
    async def concurrent_load_test(self, test_config: Dict[str, int]) -> List[SIPTestResult]:
        """Run concurrent load tests with different message types."""
        self.logger.info("Starting concurrent mixed SIP load test")
        
        tasks = []
        
        # Create tasks for different SIP methods
        if test_config.get("invites", 0) > 0:
            invite_task = self.load_test_invite(
                test_config["invites"], 
                test_config.get("invite_rate", 5)
            )
            tasks.append(invite_task)
        
        if test_config.get("registers", 0) > 0:
            register_task = self.load_test_register(
                test_config["registers"],
                test_config.get("register_rate", 3)
            )
            tasks.append(register_task)
        
        if test_config.get("options", 0) > 0:
            options_task = self.load_test_options(
                test_config["options"],
                test_config.get("options_rate", 10)
            )
            tasks.append(options_task)
        
        if test_config.get("messages", 0) > 0:
            message_task = self.load_test_message(
                test_config["messages"],
                test_config.get("message_rate", 5)
            )
            tasks.append(message_task)
        
        # Run all tests concurrently
        all_results = await asyncio.gather(*tasks)
        
        # Flatten results
        flattened_results = []
        for result_list in all_results:
            flattened_results.extend(result_list)
        
        return flattened_results
    
    def analyze_results(self, results: List[SIPTestResult], test_name: str):
        """Analyze and print SIP test results."""
        if not results:
            print(f"No results for {test_name}")
            return
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        response_times = [r.response_time for r in successful]
        
        # Group by request type
        by_type = {}
        for r in results:
            if r.request_type not in by_type:
                by_type[r.request_type] = []
            by_type[r.request_type].append(r)
        
        print(f"\n{'='*60}")
        print(f"📞 SIP Protocol Load Test: {test_name}")
        print(f"{'='*60}")
        print(f"Total Requests:     {len(results):,}")
        print(f"Successful:         {len(successful):,} ({len(successful)/len(results)*100:.2f}%)")
        print(f"Failed:             {len(failed):,}")
        
        if successful:
            import statistics
            print(f"\n📊 Response Times:")
            print(f"  Average:          {statistics.mean(response_times)*1000:.2f}ms")
            print(f"  Median:           {statistics.median(response_times)*1000:.2f}ms")
            print(f"  Min:              {min(response_times)*1000:.2f}ms")
            print(f"  Max:              {max(response_times)*1000:.2f}ms")
        
        # Breakdown by SIP method
        print(f"\n📋 Breakdown by SIP Method:")
        for method, method_results in by_type.items():
            method_successful = [r for r in method_results if r.success]
            success_rate = len(method_successful) / len(method_results) * 100
            
            avg_time = 0
            if method_successful:
                avg_times = [r.response_time for r in method_successful]
                avg_time = sum(avg_times) / len(avg_times) * 1000
            
            print(f"  {method:10} {len(method_results):6} requests, {success_rate:5.1f}% success, {avg_time:6.1f}ms avg")
        
        # Response code breakdown
        if successful:
            response_codes = {}
            for r in successful:
                if r.response_code:
                    response_codes[r.response_code] = response_codes.get(r.response_code, 0) + 1
            
            if response_codes:
                print(f"\n📈 Response Codes:")
                for code, count in sorted(response_codes.items()):
                    print(f"  {code}: {count}")
        
        # Error breakdown
        if failed:
            errors = {}
            for r in failed:
                error_key = r.error or "No response"
                errors[error_key] = errors.get(error_key, 0) + 1
            
            print(f"\n❌ Errors:")
            for error, count in errors.items():
                print(f"  {error}: {count}")


async def main():
    """Main function for SIP protocol load testing."""
    parser = argparse.ArgumentParser(description="SIP Protocol Load Testing")
    parser.add_argument("--host", default="localhost", help="SIP server host")
    parser.add_argument("--port", type=int, default=5060, help="SIP server port")
    parser.add_argument("--test", 
                       choices=["invite", "register", "options", "message", "mixed"],
                       default="mixed",
                       help="Test type")
    parser.add_argument("--count", type=int, default=100, help="Number of requests")
    parser.add_argument("--rate", type=int, default=10, help="Requests per second")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print(f"🚀 SIP Protocol Load Testing")
    print(f"Target: {args.host}:{args.port}")
    print(f"Test: {args.test}")
    print(f"Count: {args.count}")
    print(f"Rate: {args.rate} req/sec")
    print("=" * 50)
    
    tester = SIPProtocolTester(args.host, args.port)
    
    try:
        if args.test == "invite":
            results = await tester.load_test_invite(args.count, args.rate)
            tester.analyze_results(results, "INVITE Load Test")
            
        elif args.test == "register":
            results = await tester.load_test_register(args.count, args.rate)
            tester.analyze_results(results, "REGISTER Load Test")
            
        elif args.test == "options":
            results = await tester.load_test_options(args.count, args.rate)
            tester.analyze_results(results, "OPTIONS Load Test")
            
        elif args.test == "message":
            results = await tester.load_test_message(args.count, args.rate)
            tester.analyze_results(results, "MESSAGE Load Test")
            
        elif args.test == "mixed":
            # Mixed test configuration
            config = {
                "invites": args.count // 4,
                "invite_rate": max(1, args.rate // 4),
                "registers": args.count // 4,
                "register_rate": max(1, args.rate // 4),
                "options": args.count // 4,
                "options_rate": max(1, args.rate // 2),
                "messages": args.count // 4,
                "message_rate": max(1, args.rate // 4)
            }
            
            results = await tester.concurrent_load_test(config)
            tester.analyze_results(results, "Mixed SIP Protocol Load Test")
    
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
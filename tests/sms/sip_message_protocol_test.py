"""SIP MESSAGE protocol testing for SMS functionality."""
import asyncio
import socket
import time
import random
import string
import logging
import argparse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class SIPMessageResult:
    """Result of SIP MESSAGE test."""
    message_id: str
    from_number: str
    to_number: str
    message_body: str
    sent_time: float
    response_time: Optional[float]
    response_code: Optional[int]
    response_reason: Optional[str]
    success: bool
    error: Optional[str] = None


class SIPMessageTester:
    """SIP MESSAGE protocol tester for SMS functionality."""
    
    def __init__(self, sip_server_host: str, sip_server_port: int = 5060):
        self.sip_server_host = sip_server_host
        self.sip_server_port = sip_server_port
        
        # Local endpoint for testing
        self.local_host = "127.0.0.1"
        self.local_port = 5080
        
        self.logger = logging.getLogger(__name__)
        
        # Test results storage
        self.test_results: List[SIPMessageResult] = []
    
    def generate_call_id(self) -> str:
        """Generate unique Call-ID for SIP MESSAGE."""
        return f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}@smstest"
    
    def generate_via_branch(self) -> str:
        """Generate Via branch parameter."""
        return f"z9hG4bK{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}"
    
    def generate_tag(self) -> str:
        """Generate tag parameter."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def create_sip_message(self, from_number: str, to_number: str, 
                          message_body: str, message_id: str = None) -> str:
        """Create SIP MESSAGE request."""
        if message_id is None:
            message_id = f"msg-{int(time.time())}-{random.randint(1000, 9999)}"
        
        call_id = self.generate_call_id()
        branch = self.generate_via_branch()
        from_tag = self.generate_tag()
        
        # Calculate content length
        content_length = len(message_body.encode('utf-8'))
        
        sip_message = f"""MESSAGE sip:{to_number}@{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {self.local_host}:{self.local_port};branch={branch}
Max-Forwards: 70
To: <sip:{to_number}@{self.sip_server_host}>
From: <sip:{from_number}@{self.sip_server_host}>;tag={from_tag}
Call-ID: {call_id}
CSeq: 1 MESSAGE
Contact: <sip:{from_number}@{self.local_host}:{self.local_port}>
Content-Type: text/plain
Content-Length: {content_length}
User-Agent: SIP-SMS-Tester/1.0
X-Message-ID: {message_id}

{message_body}"""
        
        return sip_message.replace('\n', '\r\n')
    
    def create_multipart_sip_message(self, from_number: str, to_number: str,
                                   long_message: str, message_id: str = None) -> List[str]:
        """Create multipart SIP MESSAGE for long SMS."""
        if message_id is None:
            message_id = f"multipart-{int(time.time())}-{random.randint(1000, 9999)}"
        
        # SMS segment size (typically 160 for GSM 7-bit, 70 for Unicode)
        max_segment_size = 153  # Leave room for UDH in concatenated SMS
        
        # Split message into segments
        segments = []
        for i in range(0, len(long_message), max_segment_size):
            segment = long_message[i:i + max_segment_size]
            segments.append(segment)
        
        # Create SIP MESSAGE for each segment
        sip_messages = []
        total_segments = len(segments)
        
        for i, segment in enumerate(segments):
            segment_id = f"{message_id}-{i+1}"
            
            call_id = self.generate_call_id()
            branch = self.generate_via_branch()
            from_tag = self.generate_tag()
            
            content_length = len(segment.encode('utf-8'))
            
            sip_message = f"""MESSAGE sip:{to_number}@{self.sip_server_host} SIP/2.0
Via: SIP/2.0/UDP {self.local_host}:{self.local_port};branch={branch}
Max-Forwards: 70
To: <sip:{to_number}@{self.sip_server_host}>
From: <sip:{from_number}@{self.sip_server_host}>;tag={from_tag}
Call-ID: {call_id}
CSeq: 1 MESSAGE
Contact: <sip:{from_number}@{self.local_host}:{self.local_port}>
Content-Type: text/plain
Content-Length: {content_length}
User-Agent: SIP-SMS-Tester/1.0
X-Message-ID: {segment_id}
X-SMS-Part: {i+1}/{total_segments}
X-SMS-Reference: {message_id}

{segment}"""
            
            sip_messages.append(sip_message.replace('\n', '\r\n'))
        
        return sip_messages
    
    def parse_sip_response(self, response: str) -> Tuple[Optional[int], Optional[str]]:
        """Parse SIP response and extract status code and reason."""
        try:
            lines = response.split('\r\n')
            if lines and lines[0].startswith('SIP/2.0'):
                status_line = lines[0].split()
                if len(status_line) >= 3:
                    status_code = int(status_line[1])
                    reason_phrase = ' '.join(status_line[2:])
                    return status_code, reason_phrase
        except (ValueError, IndexError):
            pass
        return None, None
    
    async def send_sip_message(self, from_number: str, to_number: str,
                             message_body: str, message_id: str = None,
                             timeout: float = 10.0) -> SIPMessageResult:
        """Send SIP MESSAGE and wait for response."""
        if message_id is None:
            message_id = f"test-{int(time.time())}-{random.randint(1000, 9999)}"
        
        sent_time = time.time()
        
        # Create SIP MESSAGE
        sip_message = self.create_sip_message(from_number, to_number, message_body, message_id)
        
        result = SIPMessageResult(
            message_id=message_id,
            from_number=from_number,
            to_number=to_number,
            message_body=message_body,
            sent_time=sent_time,
            response_time=None,
            response_code=None,
            response_reason=None,
            success=False
        )
        
        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            
            # Send SIP MESSAGE
            sock.sendto(sip_message.encode(), (self.sip_server_host, self.sip_server_port))
            
            # Wait for response
            try:
                response_data, addr = sock.recvfrom(4096)
                response_time = time.time()
                
                result.response_time = (response_time - sent_time) * 1000  # Convert to ms
                
                # Parse response
                response = response_data.decode()
                status_code, reason_phrase = self.parse_sip_response(response)
                
                result.response_code = status_code
                result.response_reason = reason_phrase
                
                # Consider 2xx responses as success
                if status_code and 200 <= status_code < 300:
                    result.success = True
                else:
                    result.success = False
                    result.error = f"SIP error: {status_code} {reason_phrase}"
                
            except socket.timeout:
                result.response_time = timeout * 1000
                result.success = False
                result.error = "Timeout waiting for response"
            
            sock.close()
            
        except Exception as e:
            result.response_time = (time.time() - sent_time) * 1000
            result.success = False
            result.error = f"Socket error: {str(e)}"
        
        self.test_results.append(result)
        return result
    
    async def send_multipart_sip_message(self, from_number: str, to_number: str,
                                       long_message: str, message_id: str = None) -> List[SIPMessageResult]:
        """Send multipart SIP MESSAGE for long SMS."""
        if message_id is None:
            message_id = f"multipart-{int(time.time())}-{random.randint(1000, 9999)}"
        
        # Create multipart messages
        sip_messages = self.create_multipart_sip_message(from_number, to_number, long_message, message_id)
        
        results = []
        for i, sip_message in enumerate(sip_messages):
            segment_id = f"{message_id}-{i+1}"
            segment_body = sip_message.split('\r\n\r\n')[1]  # Extract message body
            
            result = await self.send_sip_message(from_number, to_number, segment_body, segment_id)
            results.append(result)
        
        return results
    
    async def test_basic_sms_sending(self, num_messages: int = 10) -> List[SIPMessageResult]:
        """Test basic SMS sending via SIP MESSAGE."""
        self.logger.info(f"Testing basic SMS sending: {num_messages} messages")
        
        results = []
        
        for i in range(num_messages):
            from_number = f"+155512345{i:02d}"
            to_number = f"+155567890{i:02d}"
            message = f"Test SMS message {i+1} via SIP MESSAGE protocol"
            
            result = await self.send_sip_message(from_number, to_number, message)
            results.append(result)
            
            # Small delay between messages
            await asyncio.sleep(0.1)
        
        return results
    
    async def test_unicode_sms(self) -> List[SIPMessageResult]:
        """Test Unicode SMS messages."""
        self.logger.info("Testing Unicode SMS messages")
        
        unicode_messages = [
            "Hello 🌟 世界",
            "Testing émojis: 😀😎🚀",
            "Русский текст",
            "العربية",
            "中文测试",
            "Ñoño niño año"
        ]
        
        results = []
        
        for i, message in enumerate(unicode_messages):
            from_number = f"+1555unicode{i}"
            to_number = "+15556789012"
            
            result = await self.send_sip_message(from_number, to_number, message)
            results.append(result)
        
        return results
    
    async def test_long_sms_segmentation(self) -> List[SIPMessageResult]:
        """Test long SMS message segmentation."""
        self.logger.info("Testing long SMS segmentation")
        
        # Create messages of various lengths
        test_cases = [
            ("Standard SMS", "A" * 160),
            ("Long SMS", "B" * 320),
            ("Very Long SMS", "C" * 500),
            ("Maximum SMS", "D" * 1600)
        ]
        
        all_results = []
        
        for case_name, message in test_cases:
            from_number = "+15551234567"
            to_number = "+15556789012"
            
            if len(message) > 160:
                # Use multipart for long messages
                results = await self.send_multipart_sip_message(from_number, to_number, message)
            else:
                # Single message
                result = await self.send_sip_message(from_number, to_number, message)
                results = [result]
            
            all_results.extend(results)
            
            self.logger.info(f"{case_name}: {len(message)} chars, {len(results)} segments")
        
        return all_results
    
    async def test_concurrent_sms(self, num_concurrent: int = 20) -> List[SIPMessageResult]:
        """Test concurrent SMS sending."""
        self.logger.info(f"Testing concurrent SMS sending: {num_concurrent} messages")
        
        # Create tasks for concurrent sending
        tasks = []
        
        for i in range(num_concurrent):
            from_number = f"+1555conc{i:03d}"
            to_number = f"+1556conc{i:03d}"
            message = f"Concurrent SMS test message {i+1}"
            
            task = self.send_sip_message(from_number, to_number, message)
            tasks.append(task)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for result in results:
            if isinstance(result, SIPMessageResult):
                valid_results.append(result)
            else:
                self.logger.error(f"Concurrent task failed: {result}")
        
        return valid_results
    
    async def test_sms_rate_limiting(self, messages_per_second: int = 10, 
                                   duration_seconds: int = 30) -> List[SIPMessageResult]:
        """Test SMS rate limiting."""
        self.logger.info(f"Testing SMS rate limiting: {messages_per_second} msg/sec for {duration_seconds}s")
        
        results = []
        message_interval = 1.0 / messages_per_second
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        message_count = 0
        
        while time.time() < end_time:
            send_start = time.time()
            
            from_number = "+15551234567"
            to_number = f"+1556rate{message_count:03d}"
            message = f"Rate limit test message {message_count}"
            
            result = await self.send_sip_message(from_number, to_number, message)
            results.append(result)
            
            message_count += 1
            
            # Control sending rate
            elapsed = time.time() - send_start
            if elapsed < message_interval:
                await asyncio.sleep(message_interval - elapsed)
        
        return results
    
    async def test_error_conditions(self) -> List[SIPMessageResult]:
        """Test various error conditions."""
        self.logger.info("Testing error conditions")
        
        error_tests = [
            # Invalid phone numbers
            ("invalid_from", "invalid", "+15556789012", "Test invalid from"),
            ("invalid_to", "+15551234567", "invalid", "Test invalid to"),
            # Empty message
            ("empty_message", "+15551234567", "+15556789012", ""),
            # Non-existent domain
            ("bad_domain", "+15551234567", "+15556789012", "Test message"),
        ]
        
        results = []
        
        for test_name, from_num, to_num, message in error_tests:
            self.logger.info(f"Testing error condition: {test_name}")
            
            result = await self.send_sip_message(from_num, to_num, message)
            results.append(result)
        
        return results
    
    def analyze_results(self, results: List[SIPMessageResult], test_name: str):
        """Analyze and print test results."""
        if not results:
            print(f"\nNo results for {test_name}")
            return
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        response_times = [r.response_time for r in successful if r.response_time is not None]
        
        print(f"\n{'='*60}")
        print(f"📱 SIP MESSAGE Test: {test_name}")
        print(f"{'='*60}")
        print(f"Total Messages:     {len(results):,}")
        print(f"Successful:         {len(successful):,} ({len(successful)/len(results)*100:.2f}%)")
        print(f"Failed:             {len(failed):,}")
        
        if response_times:
            import statistics
            print(f"\n📊 Response Times:")
            print(f"  Average:          {statistics.mean(response_times):.2f}ms")
            print(f"  Median:           {statistics.median(response_times):.2f}ms")
            print(f"  Min:              {min(response_times):.2f}ms")
            print(f"  Max:              {max(response_times):.2f}ms")
        
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
                error_key = r.error or "Unknown error"
                errors[error_key] = errors.get(error_key, 0) + 1
            
            print(f"\n❌ Errors:")
            for error, count in errors.items():
                print(f"  {error}: {count}")
    
    async def run_comprehensive_test_suite(self):
        """Run comprehensive SIP MESSAGE test suite."""
        self.logger.info("Starting comprehensive SIP MESSAGE test suite")
        
        print("📱 SIP MESSAGE Protocol Testing Suite")
        print("=" * 60)
        
        # Test 1: Basic SMS sending
        basic_results = await self.test_basic_sms_sending(10)
        self.analyze_results(basic_results, "Basic SMS Sending")
        
        # Test 2: Unicode messages
        unicode_results = await self.test_unicode_sms()
        self.analyze_results(unicode_results, "Unicode SMS Messages")
        
        # Test 3: Long message segmentation
        segmentation_results = await self.test_long_sms_segmentation()
        self.analyze_results(segmentation_results, "Long SMS Segmentation")
        
        # Test 4: Concurrent sending
        concurrent_results = await self.test_concurrent_sms(15)
        self.analyze_results(concurrent_results, "Concurrent SMS Sending")
        
        # Test 5: Rate limiting
        rate_limit_results = await self.test_sms_rate_limiting(5, 20)
        self.analyze_results(rate_limit_results, "SMS Rate Limiting")
        
        # Test 6: Error conditions
        error_results = await self.test_error_conditions()
        self.analyze_results(error_results, "Error Conditions")
        
        print(f"\n🎉 Comprehensive test completed!")
        print(f"Total SIP MESSAGE requests sent: {len(self.test_results)}")


async def main():
    """Main function for SIP MESSAGE protocol testing."""
    parser = argparse.ArgumentParser(description="SIP MESSAGE Protocol Testing")
    parser.add_argument("--host", default="localhost", help="SIP server host")
    parser.add_argument("--port", type=int, default=5060, help="SIP server port")
    parser.add_argument("--test",
                       choices=["basic", "unicode", "long", "concurrent", "rate", "errors", "all"],
                       default="all",
                       help="Test type to run")
    parser.add_argument("--count", type=int, default=10,
                       help="Number of messages for basic test")
    parser.add_argument("--rate", type=int, default=5,
                       help="Messages per second for rate test")
    parser.add_argument("--concurrent", type=int, default=15,
                       help="Number of concurrent messages")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print("🚀 SIP MESSAGE Protocol Testing")
    print(f"Target: {args.host}:{args.port}")
    print(f"Test: {args.test}")
    print("=" * 50)
    
    tester = SIPMessageTester(args.host, args.port)
    
    try:
        if args.test == "basic":
            results = await tester.test_basic_sms_sending(args.count)
            tester.analyze_results(results, "Basic SMS Sending")
            
        elif args.test == "unicode":
            results = await tester.test_unicode_sms()
            tester.analyze_results(results, "Unicode SMS Messages")
            
        elif args.test == "long":
            results = await tester.test_long_sms_segmentation()
            tester.analyze_results(results, "Long SMS Segmentation")
            
        elif args.test == "concurrent":
            results = await tester.test_concurrent_sms(args.concurrent)
            tester.analyze_results(results, "Concurrent SMS Sending")
            
        elif args.test == "rate":
            results = await tester.test_sms_rate_limiting(args.rate, 30)
            tester.analyze_results(results, "SMS Rate Limiting")
            
        elif args.test == "errors":
            results = await tester.test_error_conditions()
            tester.analyze_results(results, "Error Conditions")
            
        elif args.test == "all":
            await tester.run_comprehensive_test_suite()
    
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
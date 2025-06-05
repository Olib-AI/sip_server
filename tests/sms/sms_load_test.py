"""SMS load testing and performance benchmarking."""
import asyncio
import aiohttp
import time
import random
import string
import statistics
import logging
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
from concurrent.futures import ThreadPoolExecutor
import threading


@dataclass
class SMSLoadTestResult:
    """Result of SMS load test."""
    test_name: str
    total_messages: int
    successful_sends: int
    failed_sends: int
    success_rate: float
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    messages_per_second: float
    test_duration_seconds: float
    errors: Dict[str, int]


@dataclass
class SMSTestMessage:
    """SMS test message data."""
    message_id: str
    from_number: str
    to_number: str
    message: str
    timestamp: float
    response_time: Optional[float] = None
    success: bool = False
    error: Optional[str] = None
    status_code: Optional[int] = None


class SMSLoadTester:
    """SMS load testing utility."""
    
    def __init__(self, base_url: str, auth_token: str = None):
        self.base_url = base_url
        self.auth_token = auth_token
        self.session = None
        self.test_results: List[SMSLoadTestResult] = []
        
        # Test message templates
        self.message_templates = [
            "Hello! This is a test message {id}",
            "Load testing SMS #{id} from SIP server",
            "Test message {id} - performance testing in progress",
            "SMS load test message {id} 📱",
            "Automated test message number {id}",
            "SIP server SMS test {id} - checking performance",
            "Load test SMS {id} with unicode: 🚀 测试 ñáéíóú",
            "Performance test message {id} - checking throughput",
            "SMS test {id}: How quickly can we send messages?",
            "Testing message delivery {id} via SIP protocol"
        ]
        
        self.logger = logging.getLogger(__name__)
    
    async def start_session(self):
        """Start HTTP session for API calls."""
        headers = {
            "Content-Type": "application/json"
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        connector = aiohttp.TCPConnector(
            limit=1000,
            limit_per_host=100,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        
        self.session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
    
    async def close_session(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
    
    def generate_phone_number(self, prefix: str = "+1555") -> str:
        """Generate random phone number for testing."""
        suffix = ''.join(random.choices(string.digits, k=7))
        return f"{prefix}{suffix}"
    
    def generate_test_message(self, message_id: str) -> str:
        """Generate test message content."""
        template = random.choice(self.message_templates)
        return template.format(id=message_id)
    
    async def send_single_sms(self, from_number: str, to_number: str, 
                            message: str, message_id: str) -> SMSTestMessage:
        """Send single SMS message and measure response time."""
        start_time = time.time()
        
        sms_data = {
            "from_number": from_number,
            "to_number": to_number,
            "message": message
        }
        
        test_message = SMSTestMessage(
            message_id=message_id,
            from_number=from_number,
            to_number=to_number,
            message=message,
            timestamp=start_time
        )
        
        try:
            async with self.session.post(f"{self.base_url}/api/sms/send", 
                                       json=sms_data) as response:
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # Convert to ms
                
                test_message.response_time = response_time
                test_message.status_code = response.status
                
                if 200 <= response.status < 300:
                    test_message.success = True
                else:
                    test_message.success = False
                    response_text = await response.text()
                    test_message.error = f"HTTP {response.status}: {response_text[:100]}"
                
        except Exception as e:
            end_time = time.time()
            test_message.response_time = (end_time - start_time) * 1000
            test_message.success = False
            test_message.error = str(e)
        
        return test_message
    
    async def concurrent_sms_test(self, num_messages: int, from_number: str = None,
                                rate_limit: int = None) -> List[SMSTestMessage]:
        """Send multiple SMS messages concurrently."""
        if from_number is None:
            from_number = self.generate_phone_number("+1555")
        
        self.logger.info(f"Starting concurrent SMS test: {num_messages} messages")
        
        # Generate test messages
        tasks = []
        for i in range(num_messages):
            message_id = f"concurrent-{i:06d}"
            to_number = self.generate_phone_number("+1556")
            message = self.generate_test_message(message_id)
            
            task = self.send_single_sms(from_number, to_number, message, message_id)
            tasks.append(task)
            
            # Rate limiting
            if rate_limit and i > 0 and i % rate_limit == 0:
                await asyncio.sleep(1.0)  # Pause for 1 second every rate_limit messages
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for result in results:
            if isinstance(result, SMSTestMessage):
                valid_results.append(result)
            else:
                self.logger.error(f"Task failed with exception: {result}")
        
        return valid_results
    
    async def burst_sms_test(self, burst_size: int, num_bursts: int, 
                           burst_interval: float = 1.0) -> List[SMSTestMessage]:
        """Send SMS messages in bursts to test system response."""
        self.logger.info(f"Starting burst SMS test: {num_bursts} bursts of {burst_size} messages")
        
        all_results = []
        from_number = self.generate_phone_number("+1557")
        
        for burst_num in range(num_bursts):
            self.logger.info(f"Sending burst {burst_num + 1}/{num_bursts}")
            
            # Send burst of messages
            burst_results = await self.concurrent_sms_test(burst_size, from_number)
            all_results.extend(burst_results)
            
            # Wait between bursts (except for last burst)
            if burst_num < num_bursts - 1:
                await asyncio.sleep(burst_interval)
        
        return all_results
    
    async def sustained_load_test(self, messages_per_second: int, 
                                duration_seconds: int) -> List[SMSTestMessage]:
        """Sustained load test with controlled message rate."""
        self.logger.info(f"Starting sustained load test: {messages_per_second} msg/sec for {duration_seconds}s")
        
        all_results = []
        from_number = self.generate_phone_number("+1558")
        message_interval = 1.0 / messages_per_second
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        message_count = 0
        
        while time.time() < end_time:
            batch_start = time.time()
            
            # Send batch of messages for this second
            batch_tasks = []
            for _ in range(messages_per_second):
                if time.time() >= end_time:
                    break
                
                message_id = f"sustained-{message_count:06d}"
                to_number = self.generate_phone_number("+1559")
                message = self.generate_test_message(message_id)
                
                task = self.send_single_sms(from_number, to_number, message, message_id)
                batch_tasks.append(task)
                message_count += 1
            
            # Execute batch
            if batch_tasks:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                valid_results = [r for r in batch_results if isinstance(r, SMSTestMessage)]
                all_results.extend(valid_results)
            
            # Control timing to maintain rate
            batch_elapsed = time.time() - batch_start
            if batch_elapsed < 1.0:
                await asyncio.sleep(1.0 - batch_elapsed)
        
        return all_results
    
    async def progressive_load_test(self, start_rate: int, end_rate: int, 
                                  step_duration: int = 30) -> List[SMSTestMessage]:
        """Progressive load test with increasing message rate."""
        self.logger.info(f"Starting progressive load test: {start_rate} to {end_rate} msg/sec")
        
        all_results = []
        current_rate = start_rate
        step_size = max(1, (end_rate - start_rate) // 10)  # 10 steps
        
        while current_rate <= end_rate:
            self.logger.info(f"Testing at {current_rate} messages/second")
            
            step_results = await self.sustained_load_test(current_rate, step_duration)
            all_results.extend(step_results)
            
            current_rate += step_size
        
        return all_results
    
    async def bulk_sms_test(self, bulk_size: int, num_bulks: int) -> List[SMSTestMessage]:
        """Test bulk SMS API endpoint."""
        self.logger.info(f"Starting bulk SMS test: {num_bulks} bulks of {bulk_size} messages")
        
        all_results = []
        from_number = self.generate_phone_number("+1560")
        
        for bulk_num in range(num_bulks):
            # Prepare bulk message data
            bulk_data = {
                "from_number": from_number,
                "messages": []
            }
            
            expected_results = []
            for i in range(bulk_size):
                message_id = f"bulk-{bulk_num}-{i:03d}"
                to_number = self.generate_phone_number("+1561")
                message = self.generate_test_message(message_id)
                
                bulk_data["messages"].append({
                    "to_number": to_number,
                    "message": message
                })
                
                expected_results.append(SMSTestMessage(
                    message_id=message_id,
                    from_number=from_number,
                    to_number=to_number,
                    message=message,
                    timestamp=time.time()
                ))
            
            # Send bulk SMS
            start_time = time.time()
            try:
                async with self.session.post(f"{self.base_url}/api/sms/bulk", 
                                           json=bulk_data) as response:
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000
                    
                    if 200 <= response.status < 300:
                        # Mark all messages as successful
                        for result in expected_results:
                            result.success = True
                            result.response_time = response_time / bulk_size
                            result.status_code = response.status
                    else:
                        # Mark all messages as failed
                        response_text = await response.text()
                        error_msg = f"HTTP {response.status}: {response_text[:100]}"
                        
                        for result in expected_results:
                            result.success = False
                            result.response_time = response_time / bulk_size
                            result.status_code = response.status
                            result.error = error_msg
                            
            except Exception as e:
                end_time = time.time()
                response_time = (end_time - start_time) * 1000
                
                for result in expected_results:
                    result.success = False
                    result.response_time = response_time / bulk_size
                    result.error = str(e)
            
            all_results.extend(expected_results)
        
        return all_results
    
    async def message_size_test(self, sizes: List[int] = None, 
                              messages_per_size: int = 10) -> Dict[int, List[SMSTestMessage]]:
        """Test SMS performance with different message sizes."""
        if sizes is None:
            sizes = [50, 100, 160, 320, 500, 800, 1000, 1600]  # Characters
        
        self.logger.info(f"Starting message size test: {sizes}")
        
        size_results = {}
        from_number = self.generate_phone_number("+1562")
        
        for size in sizes:
            self.logger.info(f"Testing message size: {size} characters")
            
            # Generate message of specific size
            base_message = "A" * (size - 20)  # Leave room for message ID
            
            size_test_results = []
            for i in range(messages_per_size):
                message_id = f"size-{size}-{i:02d}"
                to_number = self.generate_phone_number("+1563")
                message = f"{base_message} {message_id}"[:size]  # Ensure exact size
                
                result = await self.send_single_sms(from_number, to_number, message, message_id)
                size_test_results.append(result)
            
            size_results[size] = size_test_results
        
        return size_results
    
    def analyze_results(self, results: List[SMSTestMessage], test_name: str) -> SMSLoadTestResult:
        """Analyze SMS test results."""
        if not results:
            return SMSLoadTestResult(
                test_name=test_name,
                total_messages=0,
                successful_sends=0,
                failed_sends=0,
                success_rate=0.0,
                avg_response_time_ms=0.0,
                min_response_time_ms=0.0,
                max_response_time_ms=0.0,
                messages_per_second=0.0,
                test_duration_seconds=0.0,
                errors={}
            )
        
        # Calculate metrics
        total_messages = len(results)
        successful_sends = sum(1 for r in results if r.success)
        failed_sends = total_messages - successful_sends
        success_rate = successful_sends / total_messages if total_messages > 0 else 0
        
        # Response time metrics
        response_times = [r.response_time for r in results if r.response_time is not None]
        avg_response_time = statistics.mean(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        
        # Test duration and throughput
        if results:
            start_time = min(r.timestamp for r in results)
            end_time = max(r.timestamp for r in results if r.response_time is not None)
            if end_time > start_time:
                test_duration = end_time - start_time
                if results[-1].response_time:
                    test_duration += results[-1].response_time / 1000  # Add last response time
            else:
                test_duration = 1.0  # Minimum duration
            
            messages_per_second = total_messages / test_duration if test_duration > 0 else 0
        else:
            test_duration = 0
            messages_per_second = 0
        
        # Error analysis
        errors = {}
        for result in results:
            if not result.success and result.error:
                error_key = result.error[:50]  # Truncate long errors
                errors[error_key] = errors.get(error_key, 0) + 1
        
        return SMSLoadTestResult(
            test_name=test_name,
            total_messages=total_messages,
            successful_sends=successful_sends,
            failed_sends=failed_sends,
            success_rate=success_rate,
            avg_response_time_ms=avg_response_time,
            min_response_time_ms=min_response_time,
            max_response_time_ms=max_response_time,
            messages_per_second=messages_per_second,
            test_duration_seconds=test_duration,
            errors=errors
        )
    
    def print_results(self, result: SMSLoadTestResult):
        """Print formatted test results."""
        print(f"\n{'='*60}")
        print(f"📱 {result.test_name}")
        print(f"{'='*60}")
        print(f"Total Messages:       {result.total_messages:,}")
        print(f"Successful:           {result.successful_sends:,} ({result.success_rate:.1%})")
        print(f"Failed:               {result.failed_sends:,}")
        print(f"Test Duration:        {result.test_duration_seconds:.2f}s")
        print(f"Throughput:           {result.messages_per_second:.2f} msg/sec")
        
        print(f"\n📊 Response Times:")
        print(f"  Average:            {result.avg_response_time_ms:.2f}ms")
        print(f"  Minimum:            {result.min_response_time_ms:.2f}ms")
        print(f"  Maximum:            {result.max_response_time_ms:.2f}ms")
        
        if result.errors:
            print(f"\n❌ Errors:")
            for error, count in result.errors.items():
                print(f"  {error}: {count}")
    
    def generate_report(self, output_file: str = "sms_load_test_report.html"):
        """Generate comprehensive HTML report."""
        if not self.test_results:
            self.logger.warning("No test results to report")
            return
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SMS Load Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #4CAF50; color: white; padding: 20px; border-radius: 5px; }}
                .summary {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .test-result {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
                .metric {{ background: white; padding: 10px; border-left: 4px solid #4CAF50; }}
                .success {{ border-left-color: #4CAF50; }}
                .warning {{ border-left-color: #FF9800; }}
                .error {{ border-left-color: #f44336; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📱 SMS Load Test Report</h1>
                <p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Total Tests: {len(self.test_results)}</p>
            </div>
        """
        
        # Overall summary
        total_messages = sum(r.total_messages for r in self.test_results)
        total_successful = sum(r.successful_sends for r in self.test_results)
        overall_success_rate = total_successful / total_messages if total_messages > 0 else 0
        
        html_content += f"""
        <div class="summary">
            <h2>📊 Overall Summary</h2>
            <div class="metrics">
                <div class="metric success">
                    <h4>Total Messages</h4>
                    <p>{total_messages:,}</p>
                </div>
                <div class="metric {'success' if overall_success_rate >= 0.95 else 'warning' if overall_success_rate >= 0.80 else 'error'}">
                    <h4>Success Rate</h4>
                    <p>{overall_success_rate:.1%}</p>
                </div>
                <div class="metric">
                    <h4>Avg Throughput</h4>
                    <p>{statistics.mean([r.messages_per_second for r in self.test_results]):.1f} msg/sec</p>
                </div>
            </div>
        </div>
        """
        
        # Individual test results
        for i, result in enumerate(self.test_results):
            success_class = "success" if result.success_rate >= 0.95 else \
                          "warning" if result.success_rate >= 0.80 else "error"
            
            html_content += f"""
            <div class="test-result">
                <h3>{result.test_name}</h3>
                <div class="metrics">
                    <div class="metric {success_class}">
                        <h4>Success Rate</h4>
                        <p>{result.success_rate:.1%}</p>
                        <small>{result.successful_sends:,} / {result.total_messages:,}</small>
                    </div>
                    <div class="metric">
                        <h4>Throughput</h4>
                        <p>{result.messages_per_second:.1f} msg/sec</p>
                        <small>Duration: {result.test_duration_seconds:.1f}s</small>
                    </div>
                    <div class="metric">
                        <h4>Response Time</h4>
                        <p>{result.avg_response_time_ms:.1f}ms avg</p>
                        <small>{result.min_response_time_ms:.1f}ms - {result.max_response_time_ms:.1f}ms</small>
                    </div>
                </div>
            """
            
            if result.errors:
                html_content += """
                <h4>Errors:</h4>
                <table>
                    <tr><th>Error</th><th>Count</th></tr>
                """
                for error, count in result.errors.items():
                    html_content += f"<tr><td>{error}</td><td>{count}</td></tr>"
                html_content += "</table>"
            
            html_content += "</div>"
        
        html_content += """
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        self.logger.info(f"Report generated: {output_file}")


async def main():
    """Main function for SMS load testing."""
    parser = argparse.ArgumentParser(description="SMS Load Testing")
    parser.add_argument("--url", default="http://localhost:8000",
                       help="Base URL of SIP server")
    parser.add_argument("--token", help="Authentication token")
    parser.add_argument("--test",
                       choices=["concurrent", "burst", "sustained", "progressive", "bulk", "sizes", "all"],
                       default="all",
                       help="Test type to run")
    parser.add_argument("--messages", type=int, default=100,
                       help="Number of messages for concurrent test")
    parser.add_argument("--rate", type=int, default=10,
                       help="Messages per second for sustained test")
    parser.add_argument("--duration", type=int, default=60,
                       help="Test duration in seconds")
    parser.add_argument("--output", default="sms_load_test_report.html",
                       help="Output report file")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print("📱 SMS Load Testing Suite")
    print(f"Target: {args.url}")
    print(f"Test: {args.test}")
    print("=" * 50)
    
    tester = SMSLoadTester(args.url, args.token)
    
    try:
        await tester.start_session()
        
        if args.test in ["concurrent", "all"]:
            print(f"🔄 Running concurrent test ({args.messages} messages)...")
            results = await tester.concurrent_sms_test(args.messages)
            analysis = tester.analyze_results(results, f"Concurrent Test ({args.messages} messages)")
            tester.print_results(analysis)
            tester.test_results.append(analysis)
        
        if args.test in ["burst", "all"]:
            print("💥 Running burst test...")
            results = await tester.burst_sms_test(burst_size=20, num_bursts=5)
            analysis = tester.analyze_results(results, "Burst Test (5 bursts of 20)")
            tester.print_results(analysis)
            tester.test_results.append(analysis)
        
        if args.test in ["sustained", "all"]:
            print(f"⏱️  Running sustained load test ({args.rate} msg/sec for {args.duration}s)...")
            results = await tester.sustained_load_test(args.rate, args.duration)
            analysis = tester.analyze_results(results, f"Sustained Load ({args.rate} msg/sec)")
            tester.print_results(analysis)
            tester.test_results.append(analysis)
        
        if args.test in ["progressive", "all"]:
            print("📈 Running progressive load test...")
            results = await tester.progressive_load_test(start_rate=5, end_rate=25)
            analysis = tester.analyze_results(results, "Progressive Load (5-25 msg/sec)")
            tester.print_results(analysis)
            tester.test_results.append(analysis)
        
        if args.test in ["bulk", "all"]:
            print("📦 Running bulk SMS test...")
            results = await tester.bulk_sms_test(bulk_size=10, num_bulks=5)
            analysis = tester.analyze_results(results, "Bulk SMS Test (5 bulks of 10)")
            tester.print_results(analysis)
            tester.test_results.append(analysis)
        
        if args.test in ["sizes", "all"]:
            print("📏 Running message size test...")
            size_results = await tester.message_size_test()
            
            for size, results in size_results.items():
                analysis = tester.analyze_results(results, f"Message Size Test ({size} chars)")
                tester.print_results(analysis)
                tester.test_results.append(analysis)
        
        # Generate report
        tester.generate_report(args.output)
        print(f"\n📋 Report generated: {args.output}")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        await tester.close_session()


if __name__ == "__main__":
    asyncio.run(main())
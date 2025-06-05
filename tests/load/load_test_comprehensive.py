"""Comprehensive load testing suite for SIP server."""
import asyncio
import aiohttp
import time
import statistics
import json
import argparse
import logging
import websockets
import random
import threading
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


@dataclass
class TestResult:
    """Result of a single test request."""
    start_time: float
    end_time: float
    response_time: float
    status_code: int
    success: bool
    error: Optional[str] = None
    content_length: int = 0
    test_type: str = ""


@dataclass
class TestSummary:
    """Summary of test results."""
    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time: float
    median_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    p99_response_time: float
    requests_per_second: float
    duration: float
    errors: Dict[str, int]


class AdvancedLoadTester:
    """Advanced load testing utility with real-time monitoring."""
    
    def __init__(self, base_url: str, auth_token: str = None):
        self.base_url = base_url
        self.auth_token = auth_token
        self.session = None
        self.results: List[TestResult] = []
        self.start_time = None
        self.end_time = None
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    async def start_session(self):
        """Start HTTP session with optimized settings."""
        headers = {
            "User-Agent": "SIP-LoadTester/1.0"
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            
        connector = aiohttp.TCPConnector(
            limit=1000,  # Total connection pool size
            limit_per_host=100,  # Connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
            
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30, connect=10),
            connector=connector
        )
        
    async def close_session(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            
    async def make_request(self, method: str, endpoint: str, test_type: str = "", **kwargs) -> TestResult:
        """Make HTTP request and record detailed metrics."""
        start_time = time.time()
        
        try:
            async with self.session.request(method, f"{self.base_url}{endpoint}", **kwargs) as response:
                content = await response.text()
                end_time = time.time()
                response_time = end_time - start_time
                
                result = TestResult(
                    start_time=start_time,
                    end_time=end_time,
                    response_time=response_time,
                    status_code=response.status,
                    success=200 <= response.status < 400,
                    content_length=len(content),
                    test_type=test_type
                )
                
                self.results.append(result)
                return result
                
        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time
            
            result = TestResult(
                start_time=start_time,
                end_time=end_time,
                response_time=response_time,
                status_code=0,
                success=False,
                error=str(e),
                test_type=test_type
            )
            
            self.results.append(result)
            return result
    
    async def ramp_up_test(self, target_rps: int, duration: int, test_func: Callable, 
                          ramp_duration: int = 30) -> List[TestResult]:
        """Gradually ramp up to target requests per second."""
        self.logger.info(f"Starting ramp-up test: {target_rps} RPS for {duration}s")
        
        results = []
        start_time = time.time()
        
        # Ramp-up phase
        for step in range(ramp_duration):
            current_rps = int((step + 1) * target_rps / ramp_duration)
            
            step_start = time.time()
            tasks = []
            
            # Create requests for this second
            for _ in range(current_rps):
                task = test_func()
                tasks.append(task)
            
            # Execute and wait for next second
            if tasks:
                step_results = await asyncio.gather(*tasks, return_exceptions=True)
                results.extend([r for r in step_results if isinstance(r, TestResult)])
            
            elapsed = time.time() - step_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
        
        # Sustained load phase
        for step in range(duration):
            step_start = time.time()
            tasks = []
            
            for _ in range(target_rps):
                task = test_func()
                tasks.append(task)
            
            if tasks:
                step_results = await asyncio.gather(*tasks, return_exceptions=True)
                results.extend([r for r in step_results if isinstance(r, TestResult)])
            
            elapsed = time.time() - step_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
        
        return results
    
    async def spike_test(self, baseline_rps: int, spike_rps: int, spike_duration: int = 30) -> List[TestResult]:
        """Test server behavior under sudden load spikes."""
        self.logger.info(f"Starting spike test: {baseline_rps} -> {spike_rps} RPS")
        
        results = []
        
        # Baseline load for 30 seconds
        for _ in range(30):
            step_start = time.time()
            tasks = [self.test_health_single() for _ in range(baseline_rps)]
            step_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend([r for r in step_results if isinstance(r, TestResult)])
            
            elapsed = time.time() - step_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
        
        # Spike load
        for _ in range(spike_duration):
            step_start = time.time()
            tasks = [self.test_health_single() for _ in range(spike_rps)]
            step_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend([r for r in step_results if isinstance(r, TestResult)])
            
            elapsed = time.time() - step_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
        
        # Return to baseline
        for _ in range(30):
            step_start = time.time()
            tasks = [self.test_health_single() for _ in range(baseline_rps)]
            step_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend([r for r in step_results if isinstance(r, TestResult)])
            
            elapsed = time.time() - step_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
        
        return results
    
    async def test_health_single(self) -> TestResult:
        """Single health check request."""
        return await self.make_request("GET", "/health", "health")
    
    async def test_call_initiation_single(self, call_id: str) -> TestResult:
        """Single call initiation request."""
        call_data = {
            "from_number": f"+15551{call_id:06d}",
            "to_number": f"+15552{call_id:06d}",
            "headers": {"X-Load-Test": "true", "X-Call-ID": call_id}
        }
        return await self.make_request("POST", "/api/calls/initiate", "call_init", json=call_data)
    
    async def test_sms_single(self, msg_id: str) -> TestResult:
        """Single SMS sending request."""
        sms_data = {
            "from_number": f"+15551{msg_id:06d}",
            "to_number": f"+15552{msg_id:06d}",
            "message": f"Load test message {msg_id}"
        }
        return await self.make_request("POST", "/api/sms/send", "sms", json=sms_data)
    
    async def test_api_endpoints_mixed(self) -> TestResult:
        """Random API endpoint test."""
        endpoints = [
            ("GET", "/health", "health"),
            ("GET", "/api/calls/active", "get_calls"),
            ("GET", "/api/numbers/blocked", "get_blocked"),
            ("GET", "/api/config/status", "status")
        ]
        
        method, endpoint, test_type = random.choice(endpoints)
        return await self.make_request(method, endpoint, test_type)
    
    async def websocket_load_test(self, num_connections: int, duration: int) -> List[TestResult]:
        """Test WebSocket connections under load."""
        self.logger.info(f"Starting WebSocket load test: {num_connections} connections for {duration}s")
        
        results = []
        
        async def websocket_connection_test(conn_id: int):
            """Test single WebSocket connection."""
            start_time = time.time()
            try:
                # Replace with actual WebSocket URL for your SIP server
                uri = f"{self.base_url.replace('http', 'ws')}/ws/test"
                
                async with websockets.connect(uri) as websocket:
                    # Send test messages
                    for i in range(10):
                        message = {
                            "type": "test",
                            "connection_id": conn_id,
                            "message_id": i,
                            "timestamp": time.time()
                        }
                        await websocket.send(json.dumps(message))
                        
                        # Wait for response
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        
                    end_time = time.time()
                    
                    result = TestResult(
                        start_time=start_time,
                        end_time=end_time,
                        response_time=end_time - start_time,
                        status_code=200,
                        success=True,
                        test_type="websocket"
                    )
                    
            except Exception as e:
                end_time = time.time()
                result = TestResult(
                    start_time=start_time,
                    end_time=end_time,
                    response_time=end_time - start_time,
                    status_code=0,
                    success=False,
                    error=str(e),
                    test_type="websocket"
                )
            
            return result
        
        # Start connections
        tasks = [websocket_connection_test(i) for i in range(num_connections)]
        
        # Run for specified duration
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=duration)
        except asyncio.TimeoutError:
            self.logger.warning("WebSocket test timed out")
            results = []
        
        return results
    
    def analyze_results(self, results: List[TestResult], test_name: str) -> TestSummary:
        """Comprehensive analysis of test results."""
        if not results:
            return None
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        response_times = [r.response_time for r in successful]
        
        # Calculate percentiles
        p95 = np.percentile(response_times, 95) if response_times else 0
        p99 = np.percentile(response_times, 99) if response_times else 0
        
        # Calculate RPS
        if results:
            duration = max(r.end_time for r in results) - min(r.start_time for r in results)
            rps = len(results) / duration if duration > 0 else 0
        else:
            duration = 0
            rps = 0
        
        # Error breakdown
        errors = {}
        for r in failed:
            error_key = f"{r.status_code}: {r.error or 'Unknown'}"
            errors[error_key] = errors.get(error_key, 0) + 1
        
        summary = TestSummary(
            test_name=test_name,
            total_requests=len(results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            success_rate=len(successful) / len(results) * 100 if results else 0,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            median_response_time=statistics.median(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            p95_response_time=p95,
            p99_response_time=p99,
            requests_per_second=rps,
            duration=duration,
            errors=errors
        )
        
        self.print_summary(summary)
        return summary
    
    def print_summary(self, summary: TestSummary):
        """Print formatted test summary."""
        print(f"\n{'='*60}")
        print(f"📊 {summary.test_name}")
        print(f"{'='*60}")
        print(f"Total Requests:     {summary.total_requests:,}")
        print(f"Successful:         {summary.successful_requests:,} ({summary.success_rate:.2f}%)")
        print(f"Failed:             {summary.failed_requests:,}")
        print(f"Duration:           {summary.duration:.2f}s")
        print(f"Requests/sec:       {summary.requests_per_second:.2f}")
        print()
        print("📈 Response Times:")
        print(f"  Average:          {summary.avg_response_time*1000:.2f}ms")
        print(f"  Median:           {summary.median_response_time*1000:.2f}ms")
        print(f"  Min:              {summary.min_response_time*1000:.2f}ms")
        print(f"  Max:              {summary.max_response_time*1000:.2f}ms")
        print(f"  95th percentile:  {summary.p95_response_time*1000:.2f}ms")
        print(f"  99th percentile:  {summary.p99_response_time*1000:.2f}ms")
        
        if summary.errors:
            print("\n❌ Errors:")
            for error, count in summary.errors.items():
                print(f"  {error}: {count}")
    
    def generate_report(self, summaries: List[TestSummary], output_dir: str = "load_test_results"):
        """Generate comprehensive test report with charts."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Generate JSON report
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "test_summaries": [asdict(summary) for summary in summaries],
            "configuration": {
                "base_url": self.base_url,
                "total_results": len(self.results)
            }
        }
        
        json_file = output_path / "load_test_report.json"
        with open(json_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        # Generate response time chart
        plt.figure(figsize=(12, 8))
        
        # Response time distribution
        plt.subplot(2, 2, 1)
        response_times = [r.response_time * 1000 for r in self.results if r.success]
        if response_times:
            plt.hist(response_times, bins=50, alpha=0.7, edgecolor='black')
            plt.xlabel('Response Time (ms)')
            plt.ylabel('Frequency')
            plt.title('Response Time Distribution')
        
        # Success rate over time
        plt.subplot(2, 2, 2)
        if self.results:
            times = [r.start_time for r in self.results]
            successes = [1 if r.success else 0 for r in self.results]
            
            # Calculate moving average
            window_size = max(1, len(self.results) // 50)
            moving_avg = []
            for i in range(len(successes)):
                start = max(0, i - window_size)
                end = min(len(successes), i + window_size)
                moving_avg.append(sum(successes[start:end]) / (end - start) * 100)
            
            plt.plot(times, moving_avg)
            plt.xlabel('Time')
            plt.ylabel('Success Rate (%)')
            plt.title('Success Rate Over Time')
        
        # RPS over time
        plt.subplot(2, 2, 3)
        if self.results:
            # Group by second
            time_buckets = {}
            for r in self.results:
                bucket = int(r.start_time)
                time_buckets[bucket] = time_buckets.get(bucket, 0) + 1
            
            if time_buckets:
                times = sorted(time_buckets.keys())
                rps_values = [time_buckets[t] for t in times]
                
                plt.plot(times, rps_values)
                plt.xlabel('Time')
                plt.ylabel('Requests per Second')
                plt.title('Throughput Over Time')
        
        # Test type breakdown
        plt.subplot(2, 2, 4)
        test_types = {}
        for r in self.results:
            test_types[r.test_type] = test_types.get(r.test_type, 0) + 1
        
        if test_types:
            plt.pie(test_types.values(), labels=test_types.keys(), autopct='%1.1f%%')
            plt.title('Request Types Distribution')
        
        plt.tight_layout()
        plt.savefig(output_path / "load_test_charts.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        # Generate HTML report
        html_report = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SIP Server Load Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .summary {{ background: #f5f5f5; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .metric {{ display: inline-block; margin: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
                .error {{ color: #d32f2f; }}
                .success {{ color: #388e3c; }}
                img {{ max-width: 100%; height: auto; }}
            </style>
        </head>
        <body>
            <h1>SIP Server Load Test Report</h1>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Target Server: {self.base_url}</p>
            
            <h2>Test Results Summary</h2>
        """
        
        for summary in summaries:
            html_report += f"""
            <div class="summary">
                <h3>{summary.test_name}</h3>
                <div class="metric">
                    <strong>Total Requests:</strong> {summary.total_requests:,}
                </div>
                <div class="metric {'success' if summary.success_rate > 95 else 'error'}">
                    <strong>Success Rate:</strong> {summary.success_rate:.2f}%
                </div>
                <div class="metric">
                    <strong>Avg Response Time:</strong> {summary.avg_response_time*1000:.2f}ms
                </div>
                <div class="metric">
                    <strong>Requests/sec:</strong> {summary.requests_per_second:.2f}
                </div>
            </div>
            """
        
        html_report += """
            <h2>Performance Charts</h2>
            <img src="load_test_charts.png" alt="Performance Charts">
        </body>
        </html>
        """
        
        html_file = output_path / "load_test_report.html"
        with open(html_file, 'w') as f:
            f.write(html_report)
        
        self.logger.info(f"Load test report generated in {output_path}")
        print(f"\n📋 Report generated: {output_path}/load_test_report.html")
    
    async def run_comprehensive_test_suite(self):
        """Run complete load testing suite."""
        self.logger.info("Starting comprehensive load test suite")
        self.start_time = time.time()
        
        summaries = []
        
        # Test 1: Health endpoint baseline
        self.logger.info("Test 1: Health endpoint baseline")
        health_tasks = [self.test_health_single() for _ in range(100)]
        health_results = await asyncio.gather(*health_tasks)
        summaries.append(self.analyze_results(health_results, "Health Endpoint Baseline"))
        
        await asyncio.sleep(5)  # Cool down
        
        # Test 2: Ramp-up test
        self.logger.info("Test 2: Ramp-up test")
        ramp_results = await self.ramp_up_test(
            target_rps=50, 
            duration=60, 
            test_func=self.test_health_single,
            ramp_duration=30
        )
        summaries.append(self.analyze_results(ramp_results, "Ramp-up Test (50 RPS)"))
        
        await asyncio.sleep(10)
        
        # Test 3: Spike test
        self.logger.info("Test 3: Spike test")
        spike_results = await self.spike_test(
            baseline_rps=10,
            spike_rps=100,
            spike_duration=30
        )
        summaries.append(self.analyze_results(spike_results, "Spike Test (10->100->10 RPS)"))
        
        await asyncio.sleep(10)
        
        # Test 4: Mixed API load
        self.logger.info("Test 4: Mixed API load test")
        mixed_tasks = [self.test_api_endpoints_mixed() for _ in range(200)]
        mixed_results = await asyncio.gather(*mixed_tasks)
        summaries.append(self.analyze_results(mixed_results, "Mixed API Load Test"))
        
        await asyncio.sleep(5)
        
        # Test 5: Call initiation stress test
        self.logger.info("Test 5: Call initiation stress test")
        call_tasks = [self.test_call_initiation_single(str(i)) for i in range(50)]
        call_results = await asyncio.gather(*call_tasks)
        summaries.append(self.analyze_results(call_results, "Call Initiation Stress Test"))
        
        await asyncio.sleep(5)
        
        # Test 6: SMS load test
        self.logger.info("Test 6: SMS load test")
        sms_tasks = [self.test_sms_single(str(i)) for i in range(75)]
        sms_results = await asyncio.gather(*sms_tasks)
        summaries.append(self.analyze_results(sms_results, "SMS Load Test"))
        
        self.end_time = time.time()
        
        # Generate comprehensive report
        self.generate_report(summaries)
        
        print(f"\n🎉 Comprehensive load test completed in {self.end_time - self.start_time:.2f} seconds")
        print(f"Total requests executed: {len(self.results):,}")


async def main():
    """Main function with advanced CLI options."""
    parser = argparse.ArgumentParser(description="Advanced SIP Server Load Testing")
    parser.add_argument("--url", default="http://localhost:8000", 
                       help="Base URL of the SIP server")
    parser.add_argument("--token", help="Authentication token")
    parser.add_argument("--test", 
                       choices=["health", "calls", "sms", "ramp", "spike", "websocket", "comprehensive"],
                       default="comprehensive",
                       help="Test type to run")
    parser.add_argument("--rps", type=int, default=50, help="Target requests per second")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--connections", type=int, default=10, help="Number of WebSocket connections")
    parser.add_argument("--output", default="load_test_results", help="Output directory for reports")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print(f"🚀 Advanced SIP Server Load Testing")
    print(f"Target: {args.url}")
    print(f"Test: {args.test}")
    print("=" * 60)
    
    tester = AdvancedLoadTester(args.url, args.token)
    
    try:
        await tester.start_session()
        
        if args.test == "health":
            tasks = [tester.test_health_single() for _ in range(args.rps * args.duration)]
            results = await asyncio.gather(*tasks)
            tester.analyze_results(results, "Health Load Test")
            
        elif args.test == "ramp":
            results = await tester.ramp_up_test(args.rps, args.duration, tester.test_health_single)
            tester.analyze_results(results, "Ramp-up Test")
            
        elif args.test == "spike":
            results = await tester.spike_test(args.rps // 5, args.rps, 30)
            tester.analyze_results(results, "Spike Test")
            
        elif args.test == "websocket":
            results = await tester.websocket_load_test(args.connections, args.duration)
            tester.analyze_results(results, "WebSocket Load Test")
            
        elif args.test == "comprehensive":
            await tester.run_comprehensive_test_suite()
            
        else:
            print(f"Test type '{args.test}' not implemented")
            
    finally:
        await tester.close_session()


if __name__ == "__main__":
    asyncio.run(main())
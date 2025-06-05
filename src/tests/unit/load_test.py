"""Load testing for SIP server."""
import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Any
import json
import argparse


class LoadTester:
    """Load testing utility for SIP server."""
    
    def __init__(self, base_url: str, auth_token: str = None):
        self.base_url = base_url
        self.auth_token = auth_token
        self.session = None
        
    async def start_session(self):
        """Start HTTP session."""
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        
    async def close_session(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            
    async def make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request and measure response time."""
        start_time = time.time()
        
        try:
            async with self.session.request(method, f"{self.base_url}{endpoint}", **kwargs) as response:
                response_time = time.time() - start_time
                content = await response.text()
                
                return {
                    "status_code": response.status,
                    "response_time": response_time,
                    "content_length": len(content),
                    "success": 200 <= response.status < 400,
                    "error": None
                }
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "status_code": 0,
                "response_time": response_time,
                "content_length": 0,
                "success": False,
                "error": str(e)
            }
            
    async def test_health_endpoint(self, num_requests: int = 100) -> List[Dict[str, Any]]:
        """Load test health endpoint."""
        print(f"Testing health endpoint with {num_requests} requests...")
        
        tasks = []
        for i in range(num_requests):
            task = self.make_request("GET", "/health")
            tasks.append(task)
            
        results = await asyncio.gather(*tasks)
        return results
        
    async def test_call_initiation(self, num_calls: int = 50) -> List[Dict[str, Any]]:
        """Load test call initiation."""
        print(f"Testing call initiation with {num_calls} requests...")
        
        tasks = []
        for i in range(num_calls):
            call_data = {
                "from_number": f"+123456{i:04d}",
                "to_number": f"+098765{i:04d}",
                "headers": {"X-Load-Test": "true"}
            }
            
            task = self.make_request(
                "POST",
                "/api/calls/initiate",
                json=call_data
            )
            tasks.append(task)
            
        results = await asyncio.gather(*tasks)
        return results
        
    async def test_sms_sending(self, num_sms: int = 100) -> List[Dict[str, Any]]:
        """Load test SMS sending."""
        print(f"Testing SMS sending with {num_sms} requests...")
        
        tasks = []
        for i in range(num_sms):
            sms_data = {
                "from_number": f"+123456{i:04d}",
                "to_number": f"+098765{i:04d}",
                "message": f"Load test message {i}"
            }
            
            task = self.make_request(
                "POST",
                "/api/sms/send",
                json=sms_data
            )
            tasks.append(task)
            
        results = await asyncio.gather(*tasks)
        return results
        
    async def test_concurrent_api_calls(self, num_concurrent: int = 50) -> List[Dict[str, Any]]:
        """Test concurrent API calls of different types."""
        print(f"Testing {num_concurrent} concurrent mixed API calls...")
        
        tasks = []
        
        # Mix of different API calls
        for i in range(num_concurrent):
            if i % 4 == 0:
                # Health check
                task = self.make_request("GET", "/health")
            elif i % 4 == 1:
                # Get active calls
                task = self.make_request("GET", "/api/calls/active")
            elif i % 4 == 2:
                # Get blocked numbers
                task = self.make_request("GET", "/api/numbers/blocked")
            else:
                # Get server status
                task = self.make_request("GET", "/api/config/status")
                
            tasks.append(task)
            
        results = await asyncio.gather(*tasks)
        return results
        
    def analyze_results(self, results: List[Dict[str, Any]], test_name: str):
        """Analyze and print test results."""
        print(f"\n=== {test_name} Results ===")
        
        if not results:
            print("No results to analyze")
            return
            
        successful_requests = [r for r in results if r["success"]]
        failed_requests = [r for r in results if not r["success"]]
        
        response_times = [r["response_time"] for r in successful_requests]
        
        print(f"Total requests: {len(results)}")
        print(f"Successful requests: {len(successful_requests)}")
        print(f"Failed requests: {len(failed_requests)}")
        print(f"Success rate: {len(successful_requests) / len(results) * 100:.2f}%")
        
        if response_times:
            print(f"Average response time: {statistics.mean(response_times):.3f}s")
            print(f"Median response time: {statistics.median(response_times):.3f}s")
            print(f"Min response time: {min(response_times):.3f}s")
            print(f"Max response time: {max(response_times):.3f}s")
            
            if len(response_times) > 1:
                print(f"Response time std dev: {statistics.stdev(response_times):.3f}s")
                
        # Show error breakdown
        if failed_requests:
            print("\nError breakdown:")
            error_counts = {}
            for req in failed_requests:
                error_key = f"{req['status_code']} - {req.get('error', 'Unknown')}"
                error_counts[error_key] = error_counts.get(error_key, 0) + 1
                
            for error, count in error_counts.items():
                print(f"  {error}: {count}")
                
    async def run_all_tests(self):
        """Run all load tests."""
        await self.start_session()
        
        try:
            # Health endpoint test
            health_results = await self.test_health_endpoint(100)
            self.analyze_results(health_results, "Health Endpoint Load Test")
            
            # Wait between tests
            await asyncio.sleep(2)
            
            # Call initiation test
            call_results = await self.test_call_initiation(25)
            self.analyze_results(call_results, "Call Initiation Load Test")
            
            await asyncio.sleep(2)
            
            # SMS sending test
            sms_results = await self.test_sms_sending(50)
            self.analyze_results(sms_results, "SMS Sending Load Test")
            
            await asyncio.sleep(2)
            
            # Concurrent mixed calls
            concurrent_results = await self.test_concurrent_api_calls(75)
            self.analyze_results(concurrent_results, "Concurrent Mixed API Load Test")
            
        finally:
            await self.close_session()


async def main():
    """Main load testing function."""
    parser = argparse.ArgumentParser(description="SIP Server Load Testing")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the SIP server (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--token",
        help="Authentication token for API calls"
    )
    parser.add_argument(
        "--test",
        choices=["health", "calls", "sms", "concurrent", "all"],
        default="all",
        help="Which test to run (default: all)"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of requests per test (default: 100)"
    )
    
    args = parser.parse_args()
    
    print(f"Starting load test against {args.url}")
    print(f"Test type: {args.test}")
    print(f"Requests per test: {args.requests}")
    print("=" * 50)
    
    tester = LoadTester(args.url, args.token)
    
    try:
        await tester.start_session()
        
        if args.test == "health":
            results = await tester.test_health_endpoint(args.requests)
            tester.analyze_results(results, "Health Endpoint Load Test")
        elif args.test == "calls":
            results = await tester.test_call_initiation(args.requests)
            tester.analyze_results(results, "Call Initiation Load Test")
        elif args.test == "sms":
            results = await tester.test_sms_sending(args.requests)
            tester.analyze_results(results, "SMS Sending Load Test")
        elif args.test == "concurrent":
            results = await tester.test_concurrent_api_calls(args.requests)
            tester.analyze_results(results, "Concurrent API Load Test")
        else:
            await tester.run_all_tests()
            
    finally:
        await tester.close_session()


if __name__ == "__main__":
    asyncio.run(main())
"""Master load test runner that orchestrates comprehensive testing."""
import asyncio
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import subprocess
import sys
import os

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.load.load_test_comprehensive import AdvancedLoadTester
from tests.load.sip_protocol_load_test import SIPProtocolTester
from tests.load.websocket_bridge_load_test import WebSocketBridgeLoadTester


class MasterLoadTestRunner:
    """Orchestrates comprehensive load testing across all SIP server components."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results = {}
        self.start_time = None
        self.end_time = None
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Test components
        self.http_tester = None
        self.sip_tester = None
        self.websocket_tester = None
        
    async def initialize_testers(self):
        """Initialize all test components."""
        self.logger.info("Initializing load testers...")
        
        # HTTP/API tester
        self.http_tester = AdvancedLoadTester(
            base_url=self.config["http"]["base_url"],
            auth_token=self.config["http"].get("auth_token")
        )
        
        # SIP protocol tester
        self.sip_tester = SIPProtocolTester(
            sip_server_host=self.config["sip"]["host"],
            sip_server_port=self.config["sip"]["port"]
        )
        
        # WebSocket bridge tester
        self.websocket_tester = WebSocketBridgeLoadTester(
            websocket_url=self.config["websocket"]["url"]
        )
        
        # Initialize HTTP session
        await self.http_tester.start_session()
    
    async def cleanup_testers(self):
        """Cleanup all test components."""
        if self.http_tester:
            await self.http_tester.close_session()
    
    async def test_system_health(self) -> Dict[str, Any]:
        """Test system health and readiness."""
        self.logger.info("Testing system health...")
        
        health_results = {}
        
        # HTTP health check
        try:
            result = await self.http_tester.test_health_single()
            health_results["http"] = {
                "status": "healthy" if result.success else "unhealthy",
                "response_time": result.response_time,
                "status_code": result.status_code
            }
        except Exception as e:
            health_results["http"] = {
                "status": "error",
                "error": str(e)
            }
        
        # SIP connectivity check
        try:
            options_result = await self.sip_tester.send_sip_request(
                self.sip_tester.create_sip_options(),
                "OPTIONS",
                timeout=10.0
            )
            health_results["sip"] = {
                "status": "healthy" if options_result.success else "unhealthy",
                "response_time": options_result.response_time,
                "response_code": options_result.response_code
            }
        except Exception as e:
            health_results["sip"] = {
                "status": "error", 
                "error": str(e)
            }
        
        # WebSocket connectivity check
        try:
            ws_result = await self.websocket_tester.single_connection_test(
                "health-check", 
                duration=5, 
                audio_rate=10
            )
            health_results["websocket"] = {
                "status": "healthy" if ws_result.success else "unhealthy",
                "duration": ws_result.duration,
                "messages_exchanged": ws_result.messages_sent + ws_result.messages_received
            }
        except Exception as e:
            health_results["websocket"] = {
                "status": "error",
                "error": str(e)
            }
        
        self.results["health_check"] = health_results
        return health_results
    
    async def run_baseline_tests(self) -> Dict[str, Any]:
        """Run baseline performance tests."""
        self.logger.info("Running baseline performance tests...")
        
        baseline_results = {}
        
        # HTTP baseline
        self.logger.info("HTTP API baseline test...")
        http_tasks = [self.http_tester.test_health_single() for _ in range(100)]
        http_baseline = await asyncio.gather(*http_tasks)
        baseline_results["http"] = self.analyze_simple_results(http_baseline, "HTTP Baseline")
        
        await asyncio.sleep(2)
        
        # SIP baseline  
        self.logger.info("SIP protocol baseline test...")
        sip_baseline = await self.sip_tester.load_test_options(50, rate=10)
        baseline_results["sip"] = self.analyze_sip_results(sip_baseline, "SIP Baseline")
        
        await asyncio.sleep(2)
        
        # WebSocket baseline
        self.logger.info("WebSocket baseline test...")
        ws_baseline = await self.websocket_tester.concurrent_connections_test(5, 30, 25)
        baseline_results["websocket"] = self.analyze_websocket_results(ws_baseline, "WebSocket Baseline")
        
        self.results["baseline"] = baseline_results
        return baseline_results
    
    async def run_load_tests(self) -> Dict[str, Any]:
        """Run comprehensive load tests."""
        self.logger.info("Running comprehensive load tests...")
        
        load_results = {}
        
        # Phase 1: HTTP Load Test
        self.logger.info("Phase 1: HTTP/API Load Testing...")
        http_load = await self.http_tester.ramp_up_test(
            target_rps=self.config["load_test"]["http_rps"],
            duration=self.config["load_test"]["duration"],
            test_func=self.http_tester.test_health_single,
            ramp_duration=30
        )
        load_results["http_load"] = self.analyze_simple_results(http_load, "HTTP Load Test")
        
        await asyncio.sleep(10)  # Cool down
        
        # Phase 2: SIP Load Test
        self.logger.info("Phase 2: SIP Protocol Load Testing...")
        sip_config = {
            "invites": self.config["load_test"]["sip_calls"],
            "invite_rate": self.config["load_test"]["sip_calls"] // 60,
            "registers": 50,
            "register_rate": 5,
            "options": 100,
            "options_rate": 20,
            "messages": 75,
            "message_rate": 10
        }
        sip_load = await self.sip_tester.concurrent_load_test(sip_config)
        load_results["sip_load"] = self.analyze_sip_results(sip_load, "SIP Load Test")
        
        await asyncio.sleep(10)
        
        # Phase 3: WebSocket Load Test
        self.logger.info("Phase 3: WebSocket Bridge Load Testing...")
        ws_load = await self.websocket_tester.concurrent_connections_test(
            self.config["load_test"]["websocket_connections"],
            self.config["load_test"]["duration"],
            50  # 50 FPS audio
        )
        load_results["websocket_load"] = self.analyze_websocket_results(ws_load, "WebSocket Load Test")
        
        await asyncio.sleep(10)
        
        # Phase 4: Mixed Load Test
        self.logger.info("Phase 4: Mixed Component Load Testing...")
        mixed_results = await self.run_mixed_load_test()
        load_results["mixed_load"] = mixed_results
        
        self.results["load_tests"] = load_results
        return load_results
    
    async def run_stress_tests(self) -> Dict[str, Any]:
        """Run stress tests to find breaking points."""
        self.logger.info("Running stress tests...")
        
        stress_results = {}
        
        # HTTP Stress Test
        self.logger.info("HTTP stress test...")
        http_stress = await self.http_tester.spike_test(
            baseline_rps=50,
            spike_rps=500,
            spike_duration=60
        )
        stress_results["http_stress"] = self.analyze_simple_results(http_stress, "HTTP Stress Test")
        
        await asyncio.sleep(15)
        
        # SIP Stress Test
        self.logger.info("SIP stress test...")
        sip_stress = await self.sip_tester.load_test_invite(200, calls_per_second=20)
        stress_results["sip_stress"] = self.analyze_sip_results(sip_stress, "SIP Stress Test")
        
        await asyncio.sleep(15)
        
        # WebSocket Stress Test
        self.logger.info("WebSocket stress test...")
        ws_stress = await self.websocket_tester.stress_test_connections(100, 60)
        stress_results["websocket_stress"] = self.analyze_websocket_results(ws_stress, "WebSocket Stress Test")
        
        self.results["stress_tests"] = stress_results
        return stress_results
    
    async def run_mixed_load_test(self) -> Dict[str, Any]:
        """Run mixed load test with all components simultaneously."""
        self.logger.info("Running mixed load test...")
        
        # Start all load tests concurrently
        http_task = self.http_tester.ramp_up_test(
            target_rps=30,
            duration=120,
            test_func=self.http_tester.test_api_endpoints_mixed,
            ramp_duration=20
        )
        
        sip_task = self.sip_tester.concurrent_load_test({
            "invites": 60,
            "invite_rate": 3,
            "options": 120,
            "options_rate": 10,
            "messages": 30,
            "message_rate": 2
        })
        
        ws_task = self.websocket_tester.concurrent_connections_test(
            20, 120, 40
        )
        
        # Run all simultaneously
        http_results, sip_results, ws_results = await asyncio.gather(
            http_task, sip_task, ws_task
        )
        
        mixed_results = {
            "http": self.analyze_simple_results(http_results, "Mixed HTTP"),
            "sip": self.analyze_sip_results(sip_results, "Mixed SIP"),
            "websocket": self.analyze_websocket_results(ws_results, "Mixed WebSocket")
        }
        
        return mixed_results
    
    def analyze_simple_results(self, results: List, test_name: str) -> Dict[str, Any]:
        """Analyze simple test results."""
        if not results:
            return {"error": "No results"}
        
        successful = [r for r in results if hasattr(r, 'success') and r.success]
        failed = [r for r in results if hasattr(r, 'success') and not r.success]
        
        response_times = [r.response_time for r in successful if hasattr(r, 'response_time')]
        
        import statistics
        
        return {
            "test_name": test_name,
            "total_requests": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100 if results else 0,
            "avg_response_time": statistics.mean(response_times) if response_times else 0,
            "median_response_time": statistics.median(response_times) if response_times else 0,
            "min_response_time": min(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0
        }
    
    def analyze_sip_results(self, results: List, test_name: str) -> Dict[str, Any]:
        """Analyze SIP test results."""
        if not results:
            return {"error": "No results"}
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        by_type = {}
        for r in results:
            if r.request_type not in by_type:
                by_type[r.request_type] = {"total": 0, "successful": 0}
            by_type[r.request_type]["total"] += 1
            if r.success:
                by_type[r.request_type]["successful"] += 1
        
        response_times = [r.response_time for r in successful]
        
        import statistics
        
        return {
            "test_name": test_name,
            "total_requests": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100 if results else 0,
            "avg_response_time": statistics.mean(response_times) if response_times else 0,
            "by_type": by_type
        }
    
    def analyze_websocket_results(self, results: List, test_name: str) -> Dict[str, Any]:
        """Analyze WebSocket test results."""
        if not results:
            return {"error": "No results"}
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        total_messages_sent = sum(r.messages_sent for r in successful)
        total_messages_received = sum(r.messages_received for r in successful)
        total_audio_frames = sum(r.audio_frames_sent for r in successful)
        
        import statistics
        
        return {
            "test_name": test_name,
            "total_connections": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100 if results else 0,
            "total_messages_sent": total_messages_sent,
            "total_messages_received": total_messages_received,
            "message_success_rate": total_messages_received / total_messages_sent * 100 if total_messages_sent else 0,
            "total_audio_frames": total_audio_frames,
            "avg_duration": statistics.mean(r.duration for r in successful) if successful else 0
        }
    
    def generate_master_report(self):
        """Generate comprehensive master report."""
        output_dir = Path("master_load_test_results")
        output_dir.mkdir(exist_ok=True)
        
        # Compile comprehensive report
        master_report = {
            "test_run_info": {
                "timestamp": datetime.now().isoformat(),
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration": self.end_time - self.start_time if self.end_time and self.start_time else 0,
                "configuration": self.config
            },
            "results": self.results,
            "summary": self.generate_summary()
        }
        
        # Save JSON report
        json_file = output_dir / "master_load_test_report.json"
        with open(json_file, 'w') as f:
            json.dump(master_report, f, indent=2)
        
        # Generate HTML report
        self.generate_html_report(master_report, output_dir)
        
        self.logger.info(f"Master load test report generated in {output_dir}")
        print(f"\n📋 Master Report: {output_dir}/master_load_test_report.html")
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate test summary."""
        summary = {
            "overall_status": "unknown",
            "components_tested": [],
            "performance_rating": "unknown",
            "recommendations": []
        }
        
        # Analyze health check
        if "health_check" in self.results:
            health = self.results["health_check"]
            healthy_components = [k for k, v in health.items() if v.get("status") == "healthy"]
            summary["components_tested"] = list(health.keys())
            
            if len(healthy_components) == len(health):
                summary["overall_status"] = "healthy"
            elif len(healthy_components) > 0:
                summary["overall_status"] = "partially_healthy"
            else:
                summary["overall_status"] = "unhealthy"
        
        # Analyze performance
        if "load_tests" in self.results:
            load_tests = self.results["load_tests"]
            success_rates = []
            
            for test_name, test_results in load_tests.items():
                if isinstance(test_results, dict) and "success_rate" in test_results:
                    success_rates.append(test_results["success_rate"])
            
            if success_rates:
                avg_success_rate = sum(success_rates) / len(success_rates)
                if avg_success_rate >= 95:
                    summary["performance_rating"] = "excellent"
                elif avg_success_rate >= 90:
                    summary["performance_rating"] = "good"
                elif avg_success_rate >= 80:
                    summary["performance_rating"] = "fair"
                else:
                    summary["performance_rating"] = "poor"
        
        # Generate recommendations
        recommendations = []
        
        if summary["overall_status"] != "healthy":
            recommendations.append("Investigate unhealthy components before production deployment")
        
        if summary["performance_rating"] in ["fair", "poor"]:
            recommendations.append("Performance optimization needed - check error rates and response times")
        
        if "stress_tests" in self.results:
            recommendations.append("Review stress test results to understand system limits")
        
        summary["recommendations"] = recommendations
        
        return summary
    
    def generate_html_report(self, master_report: Dict[str, Any], output_dir: Path):
        """Generate HTML master report."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SIP Server Master Load Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #2196F3; color: white; padding: 20px; border-radius: 5px; }}
                .summary {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .test-section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .metric {{ display: inline-block; margin: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 3px; }}
                .success {{ color: #4CAF50; }}
                .warning {{ color: #FF9800; }}
                .error {{ color: #F44336; }}
                .excellent {{ background: #C8E6C9; }}
                .good {{ background: #DCEDC8; }}
                .fair {{ background: #FFF9C4; }}
                .poor {{ background: #FFCDD2; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚀 SIP Server Master Load Test Report</h1>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Duration: {master_report['test_run_info']['duration']:.2f} seconds</p>
            </div>
            
            <div class="summary">
                <h2>📊 Test Summary</h2>
                <div class="metric">
                    <strong>Overall Status:</strong> 
                    <span class="{'success' if master_report['summary']['overall_status'] == 'healthy' else 'warning' if 'partial' in master_report['summary']['overall_status'] else 'error'}">
                        {master_report['summary']['overall_status'].replace('_', ' ').title()}
                    </span>
                </div>
                <div class="metric">
                    <strong>Performance Rating:</strong> 
                    <span class="{master_report['summary']['performance_rating']}">
                        {master_report['summary']['performance_rating'].title()}
                    </span>
                </div>
                <div class="metric">
                    <strong>Components Tested:</strong> {len(master_report['summary']['components_tested'])}
                </div>
            </div>
        """
        
        # Add health check results
        if "health_check" in master_report["results"]:
            html_content += """
            <div class="test-section">
                <h3>🏥 Health Check Results</h3>
                <table>
                    <tr><th>Component</th><th>Status</th><th>Details</th></tr>
            """
            
            for component, status in master_report["results"]["health_check"].items():
                status_class = "success" if status.get("status") == "healthy" else "error"
                details = f"Response Time: {status.get('response_time', 'N/A')}" if status.get("response_time") else status.get("error", "No details")
                
                html_content += f"""
                    <tr>
                        <td>{component.upper()}</td>
                        <td class="{status_class}">{status.get('status', 'unknown').title()}</td>
                        <td>{details}</td>
                    </tr>
                """
            
            html_content += "</table></div>"
        
        # Add load test results
        if "load_tests" in master_report["results"]:
            html_content += """
            <div class="test-section">
                <h3>📈 Load Test Results</h3>
                <table>
                    <tr><th>Test</th><th>Requests</th><th>Success Rate</th><th>Avg Response Time</th></tr>
            """
            
            for test_name, results in master_report["results"]["load_tests"].items():
                if isinstance(results, dict) and "total_requests" in results:
                    success_rate = results.get("success_rate", 0)
                    success_class = "success" if success_rate >= 95 else "warning" if success_rate >= 80 else "error"
                    
                    html_content += f"""
                        <tr>
                            <td>{test_name.replace('_', ' ').title()}</td>
                            <td>{results.get('total_requests', 0):,}</td>
                            <td class="{success_class}">{success_rate:.2f}%</td>
                            <td>{results.get('avg_response_time', 0)*1000:.2f}ms</td>
                        </tr>
                    """
            
            html_content += "</table></div>"
        
        # Add recommendations
        if master_report["summary"]["recommendations"]:
            html_content += """
            <div class="test-section">
                <h3>💡 Recommendations</h3>
                <ul>
            """
            
            for rec in master_report["summary"]["recommendations"]:
                html_content += f"<li>{rec}</li>"
            
            html_content += "</ul></div>"
        
        html_content += """
        </body>
        </html>
        """
        
        html_file = output_dir / "master_load_test_report.html"
        with open(html_file, 'w') as f:
            f.write(html_content)
    
    async def run_comprehensive_test_suite(self):
        """Run the complete test suite."""
        self.start_time = time.time()
        
        try:
            await self.initialize_testers()
            
            # Phase 1: Health checks
            print("🏥 Phase 1: System Health Check")
            await self.test_system_health()
            
            # Phase 2: Baseline tests
            print("\n📊 Phase 2: Baseline Performance Tests")
            await self.run_baseline_tests()
            
            # Phase 3: Load tests
            print("\n🔥 Phase 3: Load Tests")
            await self.run_load_tests()
            
            # Phase 4: Stress tests
            print("\n💪 Phase 4: Stress Tests")
            await self.run_stress_tests()
            
        except Exception as e:
            self.logger.error(f"Test suite failed: {e}")
            raise
        finally:
            await self.cleanup_testers()
            self.end_time = time.time()
            
            # Generate report
            self.generate_master_report()
            
            print(f"\n🎉 Master load test suite completed!")
            print(f"Total duration: {self.end_time - self.start_time:.2f} seconds")


def load_config(config_file: str) -> Dict[str, Any]:
    """Load configuration from file."""
    config_path = Path(config_file)
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    else:
        # Default configuration
        return {
            "http": {
                "base_url": "http://localhost:8000",
                "auth_token": None
            },
            "sip": {
                "host": "localhost",
                "port": 5060
            },
            "websocket": {
                "url": "ws://localhost:8080/ws"
            },
            "load_test": {
                "duration": 120,
                "http_rps": 100,
                "sip_calls": 100,
                "websocket_connections": 25
            }
        }


async def main():
    """Main function for master load testing."""
    parser = argparse.ArgumentParser(description="Master SIP Server Load Testing Suite")
    parser.add_argument("--config", default="load_test_config.json",
                       help="Configuration file path")
    parser.add_argument("--http-url", help="Override HTTP base URL")
    parser.add_argument("--sip-host", help="Override SIP host")
    parser.add_argument("--websocket-url", help="Override WebSocket URL")
    parser.add_argument("--token", help="Authentication token")
    parser.add_argument("--quick", action="store_true", 
                       help="Run quick test suite (reduced load)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Load configuration
    config = load_config(args.config)
    
    # Apply command line overrides
    if args.http_url:
        config["http"]["base_url"] = args.http_url
    if args.sip_host:
        config["sip"]["host"] = args.sip_host
    if args.websocket_url:
        config["websocket"]["url"] = args.websocket_url
    if args.token:
        config["http"]["auth_token"] = args.token
    
    # Quick test configuration
    if args.quick:
        config["load_test"]["duration"] = 30
        config["load_test"]["http_rps"] = 25
        config["load_test"]["sip_calls"] = 25
        config["load_test"]["websocket_connections"] = 5
    
    print("🚀 SIP Server Master Load Testing Suite")
    print("=" * 60)
    print(f"HTTP API: {config['http']['base_url']}")
    print(f"SIP Server: {config['sip']['host']}:{config['sip']['port']}")
    print(f"WebSocket: {config['websocket']['url']}")
    print(f"Test Mode: {'Quick' if args.quick else 'Comprehensive'}")
    print("=" * 60)
    
    runner = MasterLoadTestRunner(config)
    
    try:
        await runner.run_comprehensive_test_suite()
        
    except KeyboardInterrupt:
        print("\n⚠️  Test suite interrupted by user")
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
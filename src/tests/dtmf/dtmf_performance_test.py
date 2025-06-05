"""DTMF performance and accuracy testing suite."""
import asyncio
import time
import numpy as np
import statistics
import argparse
import logging
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass
class DTMFTestResult:
    """Result of DTMF performance test."""
    digit: str
    detection_time_ms: float
    accuracy: float
    snr_db: float
    false_positives: int
    false_negatives: int
    confidence_score: float


@dataclass
class DTMFPerformanceReport:
    """Complete DTMF performance report."""
    test_name: str
    total_tests: int
    overall_accuracy: float
    avg_detection_time_ms: float
    min_detection_time_ms: float
    max_detection_time_ms: float
    snr_range_db: Tuple[float, float]
    digit_results: Dict[str, DTMFTestResult]
    performance_score: float


class DTMFPerformanceTester:
    """Comprehensive DTMF performance testing."""
    
    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        self.logger = logging.getLogger(__name__)
        
        # Import DTMF detector (assuming it exists)
        from src.dtmf.dtmf_detector import DTMFDetector
        self.detector = DTMFDetector(sample_rate=sample_rate)
        
        # DTMF frequency mapping
        self.dtmf_frequencies = {
            '1': (697, 1209), '2': (697, 1336), '3': (697, 1477), 'A': (697, 1633),
            '4': (770, 1209), '5': (770, 1336), '6': (770, 1477), 'B': (770, 1633),
            '7': (852, 1209), '8': (852, 1336), '9': (852, 1477), 'C': (852, 1633),
            '*': (941, 1209), '0': (941, 1336), '#': (941, 1477), 'D': (941, 1633)
        }
        
        # Test results storage
        self.test_results: List[DTMFPerformanceReport] = []
    
    def generate_dtmf_tone(self, digit: str, duration: float = 0.1, 
                          amplitude: float = 0.5, phase_offset: float = 0) -> np.ndarray:
        """Generate DTMF tone with specified parameters."""
        if digit not in self.dtmf_frequencies:
            raise ValueError(f"Invalid DTMF digit: {digit}")
        
        low_freq, high_freq = self.dtmf_frequencies[digit]
        
        samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        
        # Generate dual-tone signal with optional phase offset
        low_tone = amplitude * np.sin(2 * np.pi * low_freq * t + phase_offset)
        high_tone = amplitude * np.sin(2 * np.pi * high_freq * t + phase_offset)
        
        dtmf_signal = low_tone + high_tone
        return dtmf_signal.astype(np.float32)
    
    def add_noise(self, signal: np.ndarray, snr_db: float) -> np.ndarray:
        """Add white noise to signal for specified SNR."""
        signal_power = np.mean(signal ** 2)
        noise_power = signal_power / (10 ** (snr_db / 10))
        
        noise = np.random.normal(0, np.sqrt(noise_power), len(signal))
        return signal + noise.astype(np.float32)
    
    def add_frequency_drift(self, signal: np.ndarray, max_drift_hz: float) -> np.ndarray:
        """Add frequency drift to simulate oscillator instability."""
        t = np.arange(len(signal)) / self.sample_rate
        
        # Random frequency drift
        drift_hz = np.random.uniform(-max_drift_hz, max_drift_hz)
        phase_drift = 2 * np.pi * drift_hz * t
        
        # Apply frequency modulation
        complex_signal = signal * np.exp(1j * phase_drift)
        return np.real(complex_signal).astype(np.float32)
    
    def add_amplitude_variation(self, signal: np.ndarray, variation_percent: float) -> np.ndarray:
        """Add amplitude variations to signal."""
        variation_factor = 1 + (variation_percent / 100) * (2 * np.random.random() - 1)
        return signal * variation_factor
    
    def simulate_channel_effects(self, signal: np.ndarray, 
                                channel_type: str = "telephone") -> np.ndarray:
        """Simulate various channel effects."""
        if channel_type == "telephone":
            # Telephone channel: 300-3400 Hz bandpass filter simulation
            # Apply simple high-pass and low-pass filtering
            
            # High-pass filter (remove DC and very low frequencies)
            if len(signal) > 1:
                signal = signal - np.mean(signal)
                signal[1:] = signal[1:] - 0.95 * signal[:-1]
            
            # Low-pass filter (remove high frequencies)
            # Simple moving average filter
            window = 3
            padded_signal = np.pad(signal, (window//2, window//2), mode='edge')
            filtered = np.convolve(padded_signal, np.ones(window)/window, mode='valid')
            signal = filtered[:len(signal)]
        
        elif channel_type == "cellular":
            # Cellular channel: add slight compression and distortion
            signal = np.tanh(signal * 1.2)  # Soft compression
            
        elif channel_type == "voip":
            # VoIP channel: add packet loss simulation
            packet_size = int(0.020 * self.sample_rate)  # 20ms packets
            num_packets = len(signal) // packet_size
            
            for i in range(num_packets):
                if np.random.random() < 0.01:  # 1% packet loss
                    start_idx = i * packet_size
                    end_idx = min(start_idx + packet_size, len(signal))
                    signal[start_idx:end_idx] = 0
        
        return signal
    
    async def test_digit_accuracy(self, digit: str, num_tests: int = 100,
                                snr_range: Tuple[float, float] = (10, 40)) -> DTMFTestResult:
        """Test accuracy for specific DTMF digit."""
        self.logger.info(f"Testing digit '{digit}' accuracy ({num_tests} tests)")
        
        detection_times = []
        correct_detections = 0
        false_positives = 0
        false_negatives = 0
        confidence_scores = []
        
        for test_idx in range(num_tests):
            # Random test parameters
            duration = np.random.uniform(0.08, 0.25)  # 80-250ms
            amplitude = np.random.uniform(0.1, 0.8)
            snr_db = np.random.uniform(snr_range[0], snr_range[1])
            phase_offset = np.random.uniform(0, 2 * np.pi)
            
            # Generate DTMF signal
            clean_signal = self.generate_dtmf_tone(digit, duration, amplitude, phase_offset)
            
            # Add noise and channel effects
            noisy_signal = self.add_noise(clean_signal, snr_db)
            noisy_signal = self.add_frequency_drift(noisy_signal, 2.0)  # ±2Hz drift
            noisy_signal = self.add_amplitude_variation(noisy_signal, 10)  # ±10%
            
            # Randomly apply channel effects
            channel_types = ["telephone", "cellular", "voip", "clean"]
            channel = np.random.choice(channel_types)
            if channel != "clean":
                noisy_signal = self.simulate_channel_effects(noisy_signal, channel)
            
            # Test detection
            start_time = time.time()
            try:
                detected_digits = await self.detector.process_signal(noisy_signal)
                detection_time = (time.time() - start_time) * 1000  # Convert to ms
                detection_times.append(detection_time)
                
                # Check accuracy
                if digit in detected_digits:
                    correct_detections += 1
                    confidence_scores.append(1.0)  # Simplified confidence score
                else:
                    false_negatives += 1
                    confidence_scores.append(0.0)
                
                # Check for false positives (detecting wrong digits)
                wrong_digits = set(detected_digits) - {digit}
                false_positives += len(wrong_digits)
                
            except Exception as e:
                self.logger.warning(f"Detection failed for digit {digit}: {e}")
                false_negatives += 1
                detection_times.append(0)
                confidence_scores.append(0.0)
        
        # Calculate metrics
        accuracy = correct_detections / num_tests if num_tests > 0 else 0
        avg_detection_time = statistics.mean(detection_times) if detection_times else 0
        avg_confidence = statistics.mean(confidence_scores) if confidence_scores else 0
        avg_snr = (snr_range[0] + snr_range[1]) / 2
        
        return DTMFTestResult(
            digit=digit,
            detection_time_ms=avg_detection_time,
            accuracy=accuracy,
            snr_db=avg_snr,
            false_positives=false_positives,
            false_negatives=false_negatives,
            confidence_score=avg_confidence
        )
    
    async def test_all_digits_performance(self, digits: str = "0123456789*#",
                                        tests_per_digit: int = 100) -> DTMFPerformanceReport:
        """Test performance for all DTMF digits."""
        self.logger.info(f"Testing all digits performance: {digits}")
        
        digit_results = {}
        all_detection_times = []
        total_correct = 0
        total_tests = 0
        
        for digit in digits:
            result = await self.test_digit_accuracy(digit, tests_per_digit)
            digit_results[digit] = result
            
            all_detection_times.append(result.detection_time_ms)
            total_correct += result.accuracy * tests_per_digit
            total_tests += tests_per_digit
        
        # Calculate overall metrics
        overall_accuracy = total_correct / total_tests if total_tests > 0 else 0
        avg_detection_time = statistics.mean(all_detection_times) if all_detection_times else 0
        min_detection_time = min(all_detection_times) if all_detection_times else 0
        max_detection_time = max(all_detection_times) if all_detection_times else 0
        
        # Calculate performance score (0-100)
        accuracy_score = overall_accuracy * 50  # 50 points max for accuracy
        speed_score = max(0, 50 - avg_detection_time / 2)  # 50 points max for speed
        performance_score = accuracy_score + speed_score
        
        report = DTMFPerformanceReport(
            test_name="All Digits Performance Test",
            total_tests=total_tests,
            overall_accuracy=overall_accuracy,
            avg_detection_time_ms=avg_detection_time,
            min_detection_time_ms=min_detection_time,
            max_detection_time_ms=max_detection_time,
            snr_range_db=(10, 40),
            digit_results=digit_results,
            performance_score=performance_score
        )
        
        self.test_results.append(report)
        return report
    
    async def test_noise_resistance(self, test_digit: str = "5",
                                  snr_levels: List[float] = None) -> Dict[float, DTMFTestResult]:
        """Test DTMF detection under various noise levels."""
        if snr_levels is None:
            snr_levels = [5, 10, 15, 20, 25, 30, 35, 40]
        
        self.logger.info(f"Testing noise resistance for digit '{test_digit}'")
        
        noise_results = {}
        
        for snr_db in snr_levels:
            self.logger.info(f"Testing SNR: {snr_db} dB")
            
            # Test with fixed SNR
            result = await self.test_digit_accuracy(
                test_digit, 
                num_tests=50,
                snr_range=(snr_db, snr_db)
            )
            
            noise_results[snr_db] = result
        
        return noise_results
    
    async def test_timing_accuracy(self, test_digit: str = "8") -> Dict[str, Any]:
        """Test DTMF detection timing accuracy."""
        self.logger.info(f"Testing timing accuracy for digit '{test_digit}'")
        
        # Test various durations
        durations = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30]
        timing_results = {}
        
        for duration in durations:
            correct_detections = 0
            detection_times = []
            
            for _ in range(20):  # 20 tests per duration
                signal = self.generate_dtmf_tone(test_digit, duration)
                signal = self.add_noise(signal, 25)  # 25dB SNR
                
                start_time = time.time()
                detected = await self.detector.process_signal(signal)
                detection_time = (time.time() - start_time) * 1000
                
                detection_times.append(detection_time)
                if test_digit in detected:
                    correct_detections += 1
            
            accuracy = correct_detections / 20
            avg_time = statistics.mean(detection_times)
            
            timing_results[f"{duration*1000:.0f}ms"] = {
                "accuracy": accuracy,
                "avg_detection_time_ms": avg_time,
                "duration_ms": duration * 1000
            }
        
        return timing_results
    
    async def test_concurrent_processing(self, num_concurrent: int = 50) -> Dict[str, Any]:
        """Test concurrent DTMF processing performance."""
        self.logger.info(f"Testing concurrent processing with {num_concurrent} signals")
        
        # Generate test signals
        test_signals = []
        expected_digits = []
        
        for i in range(num_concurrent):
            digit = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#"][i % 12]
            signal = self.generate_dtmf_tone(digit, 0.15)
            signal = self.add_noise(signal, 20)  # 20dB SNR
            
            test_signals.append(signal)
            expected_digits.append(digit)
        
        # Test concurrent processing
        start_time = time.time()
        
        # Process all signals concurrently
        tasks = [self.detector.process_signal(signal) for signal in test_signals]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        correct_detections = 0
        processing_errors = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processing_errors += 1
            elif expected_digits[i] in result:
                correct_detections += 1
        
        throughput = num_concurrent / total_time  # signals per second
        accuracy = correct_detections / num_concurrent
        
        return {
            "concurrent_signals": num_concurrent,
            "total_time_seconds": total_time,
            "throughput_signals_per_second": throughput,
            "accuracy": accuracy,
            "processing_errors": processing_errors,
            "avg_time_per_signal_ms": (total_time / num_concurrent) * 1000
        }
    
    async def test_stress_performance(self, duration_seconds: int = 60) -> Dict[str, Any]:
        """Stress test DTMF detection for extended period."""
        self.logger.info(f"Starting stress test for {duration_seconds} seconds")
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        total_signals = 0
        correct_detections = 0
        processing_errors = 0
        detection_times = []
        
        digits = "0123456789*#"
        
        while time.time() < end_time:
            digit = np.random.choice(list(digits))
            signal = self.generate_dtmf_tone(digit, 0.12)
            signal = self.add_noise(signal, np.random.uniform(15, 30))
            
            signal_start = time.time()
            try:
                detected = await self.detector.process_signal(signal)
                signal_end = time.time()
                
                detection_times.append((signal_end - signal_start) * 1000)
                
                if digit in detected:
                    correct_detections += 1
                    
                total_signals += 1
                
            except Exception as e:
                processing_errors += 1
                self.logger.warning(f"Processing error: {e}")
            
            # Small delay to prevent overwhelming the system
            await asyncio.sleep(0.001)
        
        actual_duration = time.time() - start_time
        
        return {
            "test_duration_seconds": actual_duration,
            "total_signals_processed": total_signals,
            "correct_detections": correct_detections,
            "processing_errors": processing_errors,
            "accuracy": correct_detections / total_signals if total_signals > 0 else 0,
            "signals_per_second": total_signals / actual_duration,
            "avg_detection_time_ms": statistics.mean(detection_times) if detection_times else 0,
            "max_detection_time_ms": max(detection_times) if detection_times else 0,
            "min_detection_time_ms": min(detection_times) if detection_times else 0
        }
    
    def generate_performance_report(self, output_file: str = "dtmf_performance_report.html"):
        """Generate comprehensive performance report."""
        if not self.test_results:
            self.logger.warning("No test results to report")
            return
        
        # Generate HTML report
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>DTMF Performance Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #2196F3; color: white; padding: 20px; border-radius: 5px; }}
                .summary {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
                .metric-card {{ background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #2196F3; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .excellent {{ border-left-color: #4CAF50; }}
                .good {{ border-left-color: #8BC34A; }}
                .fair {{ border-left-color: #FF9800; }}
                .poor {{ border-left-color: #f44336; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
                .performance-score {{ font-size: 2em; font-weight: bold; text-align: center; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📞 DTMF Performance Test Report</h1>
                <p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        """
        
        for report in self.test_results:
            # Determine performance class
            if report.performance_score >= 85:
                perf_class = "excellent"
                perf_label = "Excellent"
            elif report.performance_score >= 70:
                perf_class = "good"
                perf_label = "Good"
            elif report.performance_score >= 50:
                perf_class = "fair"
                perf_label = "Fair"
            else:
                perf_class = "poor"
                perf_label = "Poor"
            
            html_content += f"""
            <div class="summary">
                <h2>{report.test_name}</h2>
                <div class="performance-score {perf_class}">
                    Performance Score: {report.performance_score:.1f}/100 ({perf_label})
                </div>
                
                <div class="metrics">
                    <div class="metric-card">
                        <h4>Overall Accuracy</h4>
                        <p>{report.overall_accuracy:.2%}</p>
                        <small>{report.total_tests} total tests</small>
                    </div>
                    
                    <div class="metric-card">
                        <h4>Detection Speed</h4>
                        <p>{report.avg_detection_time_ms:.1f}ms avg</p>
                        <small>{report.min_detection_time_ms:.1f}ms - {report.max_detection_time_ms:.1f}ms range</small>
                    </div>
                </div>
                
                <h3>Per-Digit Results</h3>
                <table>
                    <tr>
                        <th>Digit</th>
                        <th>Accuracy</th>
                        <th>Avg Time (ms)</th>
                        <th>False Positives</th>
                        <th>False Negatives</th>
                    </tr>
            """
            
            for digit, result in report.digit_results.items():
                accuracy_class = "excellent" if result.accuracy >= 0.95 else \
                               "good" if result.accuracy >= 0.90 else \
                               "fair" if result.accuracy >= 0.80 else "poor"
                
                html_content += f"""
                    <tr>
                        <td><strong>{digit}</strong></td>
                        <td class="{accuracy_class}">{result.accuracy:.2%}</td>
                        <td>{result.detection_time_ms:.1f}</td>
                        <td>{result.false_positives}</td>
                        <td>{result.false_negatives}</td>
                    </tr>
                """
            
            html_content += "</table></div>"
        
        html_content += """
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        self.logger.info(f"Performance report generated: {output_file}")
    
    def save_results_json(self, output_file: str = "dtmf_performance_results.json"):
        """Save test results as JSON."""
        results_data = []
        
        for report in self.test_results:
            report_data = {
                "test_name": report.test_name,
                "total_tests": report.total_tests,
                "overall_accuracy": report.overall_accuracy,
                "avg_detection_time_ms": report.avg_detection_time_ms,
                "performance_score": report.performance_score,
                "digit_results": {}
            }
            
            for digit, result in report.digit_results.items():
                report_data["digit_results"][digit] = {
                    "accuracy": result.accuracy,
                    "detection_time_ms": result.detection_time_ms,
                    "false_positives": result.false_positives,
                    "false_negatives": result.false_negatives,
                    "confidence_score": result.confidence_score
                }
            
            results_data.append(report_data)
        
        with open(output_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        self.logger.info(f"Results saved to: {output_file}")


async def main():
    """Main function for DTMF performance testing."""
    parser = argparse.ArgumentParser(description="DTMF Performance Testing")
    parser.add_argument("--test-type",
                       choices=["accuracy", "noise", "timing", "concurrent", "stress", "all"],
                       default="all",
                       help="Type of performance test")
    parser.add_argument("--digits", default="0123456789*#",
                       help="Digits to test")
    parser.add_argument("--tests-per-digit", type=int, default=100,
                       help="Number of tests per digit")
    parser.add_argument("--output", default="dtmf_performance_report.html",
                       help="Output report file")
    parser.add_argument("--json-output", default="dtmf_performance_results.json",
                       help="JSON results file")
    parser.add_argument("--stress-duration", type=int, default=60,
                       help="Stress test duration in seconds")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print("📞 DTMF Performance Testing Suite")
    print(f"Test Type: {args.test_type}")
    print(f"Target Digits: {args.digits}")
    print("=" * 50)
    
    tester = DTMFPerformanceTester()
    
    try:
        if args.test_type in ["accuracy", "all"]:
            print("🎯 Running accuracy tests...")
            report = await tester.test_all_digits_performance(args.digits, args.tests_per_digit)
            
            print(f"\n📊 Overall Results:")
            print(f"Accuracy: {report.overall_accuracy:.2%}")
            print(f"Avg Detection Time: {report.avg_detection_time_ms:.1f}ms")
            print(f"Performance Score: {report.performance_score:.1f}/100")
        
        if args.test_type in ["noise", "all"]:
            print("\n🔊 Running noise resistance tests...")
            noise_results = await tester.test_noise_resistance()
            
            print("\nNoise Resistance Results:")
            for snr_db, result in noise_results.items():
                print(f"  {snr_db:2.0f}dB SNR: {result.accuracy:.2%} accuracy")
        
        if args.test_type in ["timing", "all"]:
            print("\n⏱️  Running timing accuracy tests...")
            timing_results = await tester.test_timing_accuracy()
            
            print("\nTiming Accuracy Results:")
            for duration, result in timing_results.items():
                print(f"  {duration}: {result['accuracy']:.2%} accuracy")
        
        if args.test_type in ["concurrent", "all"]:
            print("\n🔄 Running concurrent processing tests...")
            concurrent_results = await tester.test_concurrent_processing(50)
            
            print(f"\nConcurrent Processing Results:")
            print(f"  Throughput: {concurrent_results['throughput_signals_per_second']:.1f} signals/sec")
            print(f"  Accuracy: {concurrent_results['accuracy']:.2%}")
        
        if args.test_type in ["stress", "all"]:
            print(f"\n💪 Running stress test ({args.stress_duration}s)...")
            stress_results = await tester.test_stress_performance(args.stress_duration)
            
            print(f"\nStress Test Results:")
            print(f"  Signals Processed: {stress_results['total_signals_processed']}")
            print(f"  Throughput: {stress_results['signals_per_second']:.1f} signals/sec")
            print(f"  Accuracy: {stress_results['accuracy']:.2%}")
        
        # Generate reports
        tester.generate_performance_report(args.output)
        tester.save_results_json(args.json_output)
        
        print(f"\n📋 Reports generated:")
        print(f"  HTML: {args.output}")
        print(f"  JSON: {args.json_output}")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
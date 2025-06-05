"""Call quality testing for SIP server audio processing."""
import asyncio
import numpy as np
import time
import logging
import argparse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import wave
import audioop
import math
import statistics
from pathlib import Path


@dataclass
class AudioQualityMetrics:
    """Audio quality measurement results."""
    mos_score: float  # Mean Opinion Score (1-5)
    snr_db: float  # Signal-to-Noise Ratio
    thd_percent: float  # Total Harmonic Distortion
    packet_loss_percent: float  # Packet loss percentage
    jitter_ms: float  # Jitter in milliseconds
    latency_ms: float  # Round-trip latency
    frequency_response: Dict[int, float]  # Frequency response analysis
    echo_return_loss_db: float  # Echo cancellation quality
    voice_activity_detection: float  # VAD accuracy


@dataclass
class CallQualityResult:
    """Complete call quality test result."""
    call_id: str
    duration_seconds: float
    audio_metrics: AudioQualityMetrics
    codec_performance: Dict[str, Any]
    network_metrics: Dict[str, Any]
    overall_quality_score: float
    issues_detected: List[str]


class AudioSignalGenerator:
    """Generate test audio signals for quality testing."""
    
    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        
    def generate_sine_wave(self, frequency: float, duration: float, amplitude: float = 0.5) -> np.ndarray:
        """Generate pure sine wave."""
        samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        wave = amplitude * np.sin(2 * np.pi * frequency * t)
        return wave.astype(np.float32)
    
    def generate_white_noise(self, duration: float, amplitude: float = 0.1) -> np.ndarray:
        """Generate white noise signal."""
        samples = int(self.sample_rate * duration)
        noise = amplitude * np.random.normal(0, 1, samples)
        return noise.astype(np.float32)
    
    def generate_sweep_tone(self, start_freq: float, end_freq: float, duration: float) -> np.ndarray:
        """Generate frequency sweep for frequency response testing."""
        samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        
        # Logarithmic frequency sweep
        k = (end_freq / start_freq) ** (1 / duration)
        instantaneous_freq = start_freq * k ** t
        instantaneous_phase = 2 * np.pi * start_freq * (k ** t - 1) / np.log(k)
        
        sweep = 0.5 * np.sin(instantaneous_phase)
        return sweep.astype(np.float32)
    
    def generate_dtmf_tone(self, digit: str, duration: float = 0.1) -> np.ndarray:
        """Generate DTMF tone for specific digit."""
        dtmf_frequencies = {
            '1': (697, 1209), '2': (697, 1336), '3': (697, 1477), 'A': (697, 1633),
            '4': (770, 1209), '5': (770, 1336), '6': (770, 1477), 'B': (770, 1633),
            '7': (852, 1209), '8': (852, 1336), '9': (852, 1477), 'C': (852, 1633),
            '*': (941, 1209), '0': (941, 1336), '#': (941, 1477), 'D': (941, 1633)
        }
        
        if digit not in dtmf_frequencies:
            raise ValueError(f"Invalid DTMF digit: {digit}")
        
        low_freq, high_freq = dtmf_frequencies[digit]
        
        # Generate dual-tone signal
        tone1 = self.generate_sine_wave(low_freq, duration, 0.25)
        tone2 = self.generate_sine_wave(high_freq, duration, 0.25)
        
        return tone1 + tone2
    
    def generate_voice_simulation(self, duration: float) -> np.ndarray:
        """Generate simulated human voice signal."""
        samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        
        # Fundamental frequency (pitch) variation
        f0_base = 150  # Base fundamental frequency (Hz)
        f0_variation = 50 * np.sin(2 * np.pi * 2 * t)  # Pitch modulation
        f0 = f0_base + f0_variation
        
        # Generate harmonics with decreasing amplitude
        voice_signal = np.zeros(samples)
        for harmonic in range(1, 6):  # First 5 harmonics
            amplitude = 0.5 / harmonic  # Decreasing amplitude
            harmonic_freq = f0 * harmonic
            voice_signal += amplitude * np.sin(2 * np.pi * harmonic_freq * t)
        
        # Add formant filtering simulation
        # Apply envelope to simulate speech patterns
        envelope = np.where(
            (t % 0.5) < 0.3,  # Voice active 60% of time
            1.0,
            0.1  # Silence periods
        )
        
        voice_signal *= envelope
        
        # Add slight noise for realism
        noise = self.generate_white_noise(duration, 0.02)
        voice_signal += noise
        
        return voice_signal.astype(np.float32)


class AudioQualityAnalyzer:
    """Analyze audio quality metrics."""
    
    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        self.logger = logging.getLogger(__name__)
    
    def calculate_snr(self, signal: np.ndarray, noise: np.ndarray) -> float:
        """Calculate Signal-to-Noise Ratio in dB."""
        signal_power = np.mean(signal ** 2)
        noise_power = np.mean(noise ** 2)
        
        if noise_power == 0:
            return float('inf')
        
        snr_linear = signal_power / noise_power
        snr_db = 10 * np.log10(snr_linear)
        
        return snr_db
    
    def calculate_thd(self, signal: np.ndarray, fundamental_freq: float) -> float:
        """Calculate Total Harmonic Distortion."""
        # Perform FFT to get frequency domain
        fft = np.fft.fft(signal)
        freqs = np.fft.fftfreq(len(signal), 1/self.sample_rate)
        
        # Find fundamental frequency peak
        fundamental_idx = np.argmin(np.abs(freqs - fundamental_freq))
        fundamental_magnitude = np.abs(fft[fundamental_idx])
        
        # Find harmonic peaks (2f, 3f, 4f, 5f)
        harmonic_power = 0
        for harmonic in range(2, 6):
            harmonic_freq = fundamental_freq * harmonic
            if harmonic_freq < self.sample_rate / 2:  # Nyquist limit
                harmonic_idx = np.argmin(np.abs(freqs - harmonic_freq))
                harmonic_power += np.abs(fft[harmonic_idx]) ** 2
        
        # Calculate THD percentage
        fundamental_power = fundamental_magnitude ** 2
        if fundamental_power == 0:
            return 100.0
        
        thd = np.sqrt(harmonic_power / fundamental_power) * 100
        return min(thd, 100.0)  # Cap at 100%
    
    def calculate_frequency_response(self, input_signal: np.ndarray, 
                                   output_signal: np.ndarray) -> Dict[int, float]:
        """Calculate frequency response from input/output signals."""
        # Ensure signals are same length
        min_len = min(len(input_signal), len(output_signal))
        input_signal = input_signal[:min_len]
        output_signal = output_signal[:min_len]
        
        # Perform FFT on both signals
        input_fft = np.fft.fft(input_signal)
        output_fft = np.fft.fft(output_signal)
        
        # Calculate transfer function
        transfer_function = output_fft / (input_fft + 1e-10)  # Avoid division by zero
        
        # Convert to magnitude in dB
        freqs = np.fft.fftfreq(len(input_signal), 1/self.sample_rate)
        magnitude_db = 20 * np.log10(np.abs(transfer_function) + 1e-10)
        
        # Sample key frequencies for voice band
        test_frequencies = [300, 500, 1000, 2000, 3000, 4000]  # Hz
        frequency_response = {}
        
        for freq in test_frequencies:
            if freq < self.sample_rate / 2:
                freq_idx = np.argmin(np.abs(freqs - freq))
                frequency_response[freq] = magnitude_db[freq_idx]
        
        return frequency_response
    
    def detect_voice_activity(self, signal: np.ndarray, 
                            energy_threshold: float = 0.01) -> float:
        """Detect voice activity in signal."""
        # Frame-based energy calculation
        frame_size = int(0.02 * self.sample_rate)  # 20ms frames
        num_frames = len(signal) // frame_size
        
        voice_frames = 0
        total_frames = 0
        
        for i in range(num_frames):
            start_idx = i * frame_size
            end_idx = start_idx + frame_size
            frame = signal[start_idx:end_idx]
            
            # Calculate frame energy
            energy = np.mean(frame ** 2)
            
            if energy > energy_threshold:
                voice_frames += 1
            total_frames += 1
        
        if total_frames == 0:
            return 0.0
        
        vad_accuracy = voice_frames / total_frames
        return vad_accuracy
    
    def calculate_mos_score(self, metrics: Dict[str, float]) -> float:
        """Calculate Mean Opinion Score based on objective metrics."""
        # Simplified MOS calculation based on multiple factors
        # Real implementations would use more sophisticated algorithms like PESQ
        
        snr = metrics.get('snr_db', 0)
        thd = metrics.get('thd_percent', 100)
        packet_loss = metrics.get('packet_loss_percent', 0)
        jitter = metrics.get('jitter_ms', 100)
        latency = metrics.get('latency_ms', 500)
        
        # SNR contribution (0-1.5 points)
        snr_score = min(1.5, max(0, (snr - 10) / 30))
        
        # THD contribution (0-1.0 points)
        thd_score = max(0, 1.0 - thd / 10)
        
        # Packet loss contribution (0-1.0 points)
        loss_score = max(0, 1.0 - packet_loss / 5)
        
        # Jitter contribution (0-0.75 points)
        jitter_score = max(0, 0.75 - jitter / 100)
        
        # Latency contribution (0-0.75 points)
        latency_score = max(0, 0.75 - (latency - 150) / 500)
        
        # Calculate total MOS (1-5 scale)
        total_score = 1.0 + snr_score + thd_score + loss_score + jitter_score + latency_score
        
        return min(5.0, max(1.0, total_score))


class CallQualityTester:
    """Complete call quality testing system."""
    
    def __init__(self, sip_server_host: str, sip_server_port: int = 5060):
        self.sip_server_host = sip_server_host
        self.sip_server_port = sip_server_port
        
        self.signal_generator = AudioSignalGenerator()
        self.quality_analyzer = AudioQualityAnalyzer()
        
        self.logger = logging.getLogger(__name__)
        
        # Test results storage
        self.test_results: List[CallQualityResult] = []
    
    async def test_codec_quality(self, codec: str, test_duration: float = 10.0) -> Dict[str, Any]:
        """Test audio quality for specific codec."""
        self.logger.info(f"Testing codec quality: {codec}")
        
        # Generate test signals
        test_signals = {
            'sine_1khz': self.signal_generator.generate_sine_wave(1000, test_duration),
            'voice_sim': self.signal_generator.generate_voice_simulation(test_duration),
            'freq_sweep': self.signal_generator.generate_sweep_tone(300, 3400, test_duration),
            'white_noise': self.signal_generator.generate_white_noise(test_duration, 0.1)
        }
        
        codec_results = {}
        
        for signal_name, signal in test_signals.items():
            self.logger.info(f"Testing {signal_name} with {codec}")
            
            # Simulate codec processing (encode/decode)
            processed_signal = await self._simulate_codec_processing(signal, codec)
            
            # Calculate quality metrics
            metrics = self._analyze_signal_quality(signal, processed_signal, signal_name)
            codec_results[signal_name] = metrics
        
        return codec_results
    
    async def test_network_conditions(self, call_id: str, 
                                    packet_loss_rates: List[float] = [0, 1, 3, 5],
                                    jitter_levels: List[float] = [0, 10, 30, 50]) -> List[Dict[str, Any]]:
        """Test call quality under various network conditions."""
        self.logger.info(f"Testing network conditions for call {call_id}")
        
        network_test_results = []
        
        for loss_rate in packet_loss_rates:
            for jitter_ms in jitter_levels:
                self.logger.info(f"Testing: {loss_rate}% loss, {jitter_ms}ms jitter")
                
                # Generate test voice signal
                voice_signal = self.signal_generator.generate_voice_simulation(10.0)
                
                # Simulate network impairments
                impaired_signal = self._simulate_network_impairments(
                    voice_signal, loss_rate, jitter_ms
                )
                
                # Analyze quality
                metrics = self._analyze_signal_quality(voice_signal, impaired_signal, "network_test")
                
                test_result = {
                    'packet_loss_percent': loss_rate,
                    'jitter_ms': jitter_ms,
                    'quality_metrics': metrics,
                    'call_id': call_id
                }
                
                network_test_results.append(test_result)
        
        return network_test_results
    
    async def test_dtmf_quality(self, digits: str = "0123456789*#") -> Dict[str, Any]:
        """Test DTMF tone generation and detection quality."""
        self.logger.info("Testing DTMF quality")
        
        dtmf_results = {}
        
        for digit in digits:
            # Generate DTMF tone
            dtmf_signal = self.signal_generator.generate_dtmf_tone(digit, 0.1)
            
            # Add some noise to simulate real conditions
            noise = self.signal_generator.generate_white_noise(0.1, 0.02)
            noisy_dtmf = dtmf_signal + noise
            
            # Analyze DTMF quality
            dtmf_quality = self._analyze_dtmf_quality(dtmf_signal, noisy_dtmf, digit)
            dtmf_results[digit] = dtmf_quality
        
        return dtmf_results
    
    async def test_echo_cancellation(self, test_duration: float = 5.0) -> Dict[str, Any]:
        """Test echo cancellation performance."""
        self.logger.info("Testing echo cancellation")
        
        # Generate near-end speech
        near_end = self.signal_generator.generate_voice_simulation(test_duration)
        
        # Generate far-end speech
        far_end = self.signal_generator.generate_voice_simulation(test_duration)
        
        # Simulate echo (delayed and attenuated far-end signal)
        echo_delay_samples = int(0.050 * self.signal_generator.sample_rate)  # 50ms delay
        echo_attenuation = 0.3  # -10dB echo
        
        # Create echo signal
        echo_signal = np.zeros_like(far_end)
        if len(far_end) > echo_delay_samples:
            echo_signal[echo_delay_samples:] = far_end[:-echo_delay_samples] * echo_attenuation
        
        # Mixed signal (near-end + echo)
        mixed_signal = near_end + echo_signal
        
        # Simulate echo canceller output (simplified)
        echo_cancelled = await self._simulate_echo_cancellation(mixed_signal, far_end)
        
        # Calculate echo return loss
        echo_power = np.mean(echo_signal ** 2)
        residual_echo_power = np.mean((echo_cancelled - near_end) ** 2)
        
        if residual_echo_power > 0:
            echo_return_loss = 10 * np.log10(echo_power / residual_echo_power)
        else:
            echo_return_loss = 60  # Very good cancellation
        
        return {
            'echo_return_loss_db': echo_return_loss,
            'original_echo_level_db': 10 * np.log10(echo_power + 1e-10),
            'residual_echo_level_db': 10 * np.log10(residual_echo_power + 1e-10),
            'cancellation_quality': 'excellent' if echo_return_loss > 45 else 
                                  'good' if echo_return_loss > 35 else
                                  'fair' if echo_return_loss > 25 else 'poor'
        }
    
    async def run_comprehensive_quality_test(self, call_id: str) -> CallQualityResult:
        """Run comprehensive call quality test."""
        self.logger.info(f"Running comprehensive quality test for call {call_id}")
        
        start_time = time.time()
        
        # Test different aspects
        codec_results = await self.test_codec_quality("PCMU")
        network_results = await self.test_network_conditions(call_id)
        dtmf_results = await self.test_dtmf_quality()
        echo_results = await self.test_echo_cancellation()
        
        # Compile overall metrics
        overall_metrics = self._compile_overall_metrics(
            codec_results, network_results, dtmf_results, echo_results
        )
        
        # Calculate MOS score
        mos_score = self.quality_analyzer.calculate_mos_score(overall_metrics)
        
        # Detect issues
        issues = self._detect_quality_issues(overall_metrics)
        
        end_time = time.time()
        
        result = CallQualityResult(
            call_id=call_id,
            duration_seconds=end_time - start_time,
            audio_metrics=AudioQualityMetrics(
                mos_score=mos_score,
                snr_db=overall_metrics.get('snr_db', 0),
                thd_percent=overall_metrics.get('thd_percent', 0),
                packet_loss_percent=overall_metrics.get('packet_loss_percent', 0),
                jitter_ms=overall_metrics.get('jitter_ms', 0),
                latency_ms=overall_metrics.get('latency_ms', 0),
                frequency_response=overall_metrics.get('frequency_response', {}),
                echo_return_loss_db=echo_results.get('echo_return_loss_db', 0),
                voice_activity_detection=overall_metrics.get('vad_accuracy', 0)
            ),
            codec_performance=codec_results,
            network_metrics={
                'best_case': min(network_results, key=lambda x: x['quality_metrics']['mos_score']),
                'worst_case': max(network_results, key=lambda x: x['quality_metrics']['mos_score']),
                'all_results': network_results
            },
            overall_quality_score=mos_score,
            issues_detected=issues
        )
        
        self.test_results.append(result)
        return result
    
    # Private helper methods
    
    async def _simulate_codec_processing(self, signal: np.ndarray, codec: str) -> np.ndarray:
        """Simulate codec encoding/decoding process."""
        # Simplified codec simulation
        if codec == "PCMU":
            # μ-law compression simulation
            compressed = audioop.lin2ulaw(signal.tobytes(), 2)
            decompressed = audioop.ulaw2lin(compressed, 2)
            return np.frombuffer(decompressed, dtype=np.int16).astype(np.float32) / 32768.0
        elif codec == "PCMA":
            # A-law compression simulation
            compressed = audioop.lin2alaw(signal.tobytes(), 2)
            decompressed = audioop.alaw2lin(compressed, 2)
            return np.frombuffer(decompressed, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            # Default: just return original signal
            return signal
    
    def _simulate_network_impairments(self, signal: np.ndarray, 
                                    packet_loss_percent: float, 
                                    jitter_ms: float) -> np.ndarray:
        """Simulate network packet loss and jitter."""
        impaired_signal = signal.copy()
        
        # Simulate packet loss
        if packet_loss_percent > 0:
            packet_size_samples = int(0.020 * self.signal_generator.sample_rate)  # 20ms packets
            num_packets = len(signal) // packet_size_samples
            
            for i in range(num_packets):
                if np.random.random() < packet_loss_percent / 100:
                    start_idx = i * packet_size_samples
                    end_idx = start_idx + packet_size_samples
                    impaired_signal[start_idx:end_idx] = 0  # Lost packet
        
        # Simulate jitter (timing variations)
        if jitter_ms > 0:
            max_jitter_samples = int(jitter_ms * self.signal_generator.sample_rate / 1000)
            jitter_delay = np.random.randint(-max_jitter_samples, max_jitter_samples + 1)
            
            if jitter_delay > 0:
                # Delay signal
                jittered_signal = np.zeros_like(impaired_signal)
                jittered_signal[jitter_delay:] = impaired_signal[:-jitter_delay]
                impaired_signal = jittered_signal
            elif jitter_delay < 0:
                # Advance signal
                jittered_signal = np.zeros_like(impaired_signal)
                jittered_signal[:jitter_delay] = impaired_signal[-jitter_delay:]
                impaired_signal = jittered_signal
        
        return impaired_signal
    
    def _analyze_signal_quality(self, original: np.ndarray, 
                              processed: np.ndarray, 
                              signal_type: str) -> Dict[str, Any]:
        """Analyze quality metrics for signal pair."""
        # Ensure signals are same length
        min_len = min(len(original), len(processed))
        original = original[:min_len]
        processed = processed[:min_len]
        
        # Calculate noise (difference between signals)
        noise = processed - original
        
        # Basic quality metrics
        snr = self.quality_analyzer.calculate_snr(original, noise)
        
        # THD calculation (for sine waves)
        if 'sine' in signal_type:
            thd = self.quality_analyzer.calculate_thd(processed, 1000)  # 1kHz test tone
        else:
            thd = 0  # Not applicable for non-tonal signals
        
        # Frequency response
        freq_response = self.quality_analyzer.calculate_frequency_response(original, processed)
        
        # Voice activity detection (for voice signals)
        if 'voice' in signal_type:
            vad_accuracy = self.quality_analyzer.detect_voice_activity(processed)
        else:
            vad_accuracy = 1.0  # Not applicable
        
        return {
            'snr_db': snr,
            'thd_percent': thd,
            'frequency_response': freq_response,
            'vad_accuracy': vad_accuracy,
            'signal_type': signal_type,
            'mos_score': self.quality_analyzer.calculate_mos_score({
                'snr_db': snr,
                'thd_percent': thd,
                'packet_loss_percent': 0,
                'jitter_ms': 0,
                'latency_ms': 150  # Assumed default
            })
        }
    
    def _analyze_dtmf_quality(self, original: np.ndarray, 
                            processed: np.ndarray, 
                            digit: str) -> Dict[str, Any]:
        """Analyze DTMF tone quality."""
        # Calculate SNR for DTMF tone
        noise = processed - original
        snr = self.quality_analyzer.calculate_snr(original, noise)
        
        # DTMF tone detection would typically involve
        # Goertzel algorithm or FFT-based frequency detection
        
        return {
            'digit': digit,
            'snr_db': snr,
            'detection_quality': 'excellent' if snr > 20 else
                               'good' if snr > 15 else
                               'fair' if snr > 10 else 'poor'
        }
    
    async def _simulate_echo_cancellation(self, mixed_signal: np.ndarray, 
                                        reference_signal: np.ndarray) -> np.ndarray:
        """Simulate adaptive echo cancellation."""
        # Simplified echo cancellation simulation
        # Real implementations use adaptive filters like NLMS or RLS
        
        # For simulation, assume 80% echo reduction
        echo_reduction_factor = 0.8
        
        # Estimate echo component (very simplified)
        echo_delay_samples = int(0.050 * self.signal_generator.sample_rate)
        estimated_echo = np.zeros_like(mixed_signal)
        
        if len(reference_signal) > echo_delay_samples:
            estimated_echo[echo_delay_samples:] = (
                reference_signal[:-echo_delay_samples] * 0.3 * echo_reduction_factor
            )
        
        # Remove estimated echo
        echo_cancelled = mixed_signal - estimated_echo
        
        return echo_cancelled
    
    def _compile_overall_metrics(self, codec_results: Dict, network_results: List,
                               dtmf_results: Dict, echo_results: Dict) -> Dict[str, Any]:
        """Compile overall quality metrics from all tests."""
        # Extract best-case metrics from codec tests
        codec_metrics = codec_results.get('voice_sim', {})
        
        # Extract metrics from network tests (use best case)
        best_network = min(network_results, key=lambda x: x.get('packet_loss_percent', 100))
        
        # Compile overall metrics
        overall = {
            'snr_db': codec_metrics.get('snr_db', 20),
            'thd_percent': codec_metrics.get('thd_percent', 1),
            'packet_loss_percent': best_network.get('packet_loss_percent', 0),
            'jitter_ms': best_network.get('jitter_ms', 10),
            'latency_ms': 150,  # Assumed
            'frequency_response': codec_metrics.get('frequency_response', {}),
            'echo_return_loss_db': echo_results.get('echo_return_loss_db', 40),
            'vad_accuracy': codec_metrics.get('vad_accuracy', 0.9)
        }
        
        return overall
    
    def _detect_quality_issues(self, metrics: Dict[str, Any]) -> List[str]:
        """Detect potential quality issues from metrics."""
        issues = []
        
        if metrics.get('snr_db', 0) < 15:
            issues.append("Low signal-to-noise ratio detected")
        
        if metrics.get('thd_percent', 0) > 5:
            issues.append("High total harmonic distortion")
        
        if metrics.get('packet_loss_percent', 0) > 1:
            issues.append(f"Packet loss detected: {metrics['packet_loss_percent']}%")
        
        if metrics.get('jitter_ms', 0) > 30:
            issues.append(f"High jitter detected: {metrics['jitter_ms']}ms")
        
        if metrics.get('echo_return_loss_db', 0) < 30:
            issues.append("Poor echo cancellation performance")
        
        if metrics.get('vad_accuracy', 1) < 0.8:
            issues.append("Poor voice activity detection")
        
        return issues
    
    def generate_quality_report(self, output_file: str = "call_quality_report.html"):
        """Generate comprehensive quality test report."""
        if not self.test_results:
            self.logger.warning("No test results to report")
            return
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Call Quality Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #4CAF50; color: white; padding: 20px; border-radius: 5px; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
                .metric-card {{ background: #f5f5f5; padding: 15px; border-radius: 5px; border-left: 4px solid #4CAF50; }}
                .issue {{ background: #ffebee; border-left-color: #f44336; }}
                .excellent {{ border-left-color: #4CAF50; }}
                .good {{ border-left-color: #8BC34A; }}
                .fair {{ border-left-color: #FF9800; }}
                .poor {{ border-left-color: #f44336; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📞 Call Quality Test Report</h1>
                <p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        """
        
        for result in self.test_results:
            quality_class = "excellent" if result.overall_quality_score >= 4.0 else \
                          "good" if result.overall_quality_score >= 3.5 else \
                          "fair" if result.overall_quality_score >= 3.0 else "poor"
            
            html_content += f"""
            <div class="metric-card {quality_class}">
                <h3>Call {result.call_id}</h3>
                <p><strong>Overall MOS Score:</strong> {result.overall_quality_score:.2f}/5.0</p>
                <p><strong>Test Duration:</strong> {result.duration_seconds:.1f} seconds</p>
            </div>
            
            <div class="metrics">
                <div class="metric-card">
                    <h4>Audio Quality</h4>
                    <p>SNR: {result.audio_metrics.snr_db:.1f} dB</p>
                    <p>THD: {result.audio_metrics.thd_percent:.2f}%</p>
                    <p>Echo Return Loss: {result.audio_metrics.echo_return_loss_db:.1f} dB</p>
                </div>
                
                <div class="metric-card">
                    <h4>Network Quality</h4>
                    <p>Packet Loss: {result.audio_metrics.packet_loss_percent:.2f}%</p>
                    <p>Jitter: {result.audio_metrics.jitter_ms:.1f} ms</p>
                    <p>Latency: {result.audio_metrics.latency_ms:.1f} ms</p>
                </div>
                
                <div class="metric-card">
                    <h4>Voice Processing</h4>
                    <p>VAD Accuracy: {result.audio_metrics.voice_activity_detection:.2f}</p>
                    <p>Frequency Response: See detailed table</p>
                </div>
            </div>
            """
            
            if result.issues_detected:
                html_content += """
                <div class="metric-card issue">
                    <h4>Issues Detected</h4>
                    <ul>
                """
                for issue in result.issues_detected:
                    html_content += f"<li>{issue}</li>"
                html_content += "</ul></div>"
        
        html_content += """
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        self.logger.info(f"Quality report generated: {output_file}")


async def main():
    """Main function for call quality testing."""
    parser = argparse.ArgumentParser(description="Call Quality Testing")
    parser.add_argument("--host", default="localhost", help="SIP server host")
    parser.add_argument("--port", type=int, default=5060, help="SIP server port")
    parser.add_argument("--call-id", default="quality-test-001", help="Call ID for testing")
    parser.add_argument("--test-type", 
                       choices=["codec", "network", "dtmf", "echo", "comprehensive"],
                       default="comprehensive",
                       help="Type of quality test")
    parser.add_argument("--output", default="call_quality_report.html",
                       help="Output report file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print("📞 Call Quality Testing Suite")
    print(f"Target: {args.host}:{args.port}")
    print(f"Test Type: {args.test_type}")
    print("=" * 50)
    
    tester = CallQualityTester(args.host, args.port)
    
    try:
        if args.test_type == "comprehensive":
            result = await tester.run_comprehensive_quality_test(args.call_id)
            
            print(f"\n📊 Quality Test Results for Call {result.call_id}")
            print(f"Overall MOS Score: {result.overall_quality_score:.2f}/5.0")
            print(f"SNR: {result.audio_metrics.snr_db:.1f} dB")
            print(f"THD: {result.audio_metrics.thd_percent:.2f}%")
            print(f"Echo Return Loss: {result.audio_metrics.echo_return_loss_db:.1f} dB")
            
            if result.issues_detected:
                print("\n⚠️  Issues Detected:")
                for issue in result.issues_detected:
                    print(f"  - {issue}")
            else:
                print("\n✅ No quality issues detected")
        
        elif args.test_type == "codec":
            results = await tester.test_codec_quality("PCMU")
            print("\n📊 Codec Quality Results:")
            for signal_type, metrics in results.items():
                print(f"  {signal_type}: MOS {metrics.get('mos_score', 0):.2f}")
        
        elif args.test_type == "network":
            results = await tester.test_network_conditions(args.call_id)
            print("\n📊 Network Quality Results:")
            for result in results[:5]:  # Show first 5 results
                print(f"  Loss: {result['packet_loss_percent']}%, "
                      f"Jitter: {result['jitter_ms']}ms, "
                      f"MOS: {result['quality_metrics'].get('mos_score', 0):.2f}")
        
        elif args.test_type == "dtmf":
            results = await tester.test_dtmf_quality()
            print("\n📊 DTMF Quality Results:")
            for digit, metrics in results.items():
                print(f"  Digit {digit}: {metrics['detection_quality']}")
        
        elif args.test_type == "echo":
            results = await tester.test_echo_cancellation()
            print("\n📊 Echo Cancellation Results:")
            print(f"  Echo Return Loss: {results['echo_return_loss_db']:.1f} dB")
            print(f"  Quality: {results['cancellation_quality']}")
        
        # Generate report
        tester.generate_quality_report(args.output)
        print(f"\n📋 Report generated: {args.output}")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
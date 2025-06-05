"""Comprehensive DTMF functionality testing suite."""
import pytest
import asyncio
import numpy as np
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any, Tuple, Optional

# Import DTMF modules
from src.dtmf.dtmf_detector import DTMFDetector
from src.dtmf.dtmf_processor import DTMFProcessor
from src.dtmf.ivr_manager import IVRManager
from src.dtmf.music_on_hold import MusicOnHold


class DTMFSignalGenerator:
    """Generate DTMF signals for testing."""
    
    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = sample_rate
        
        # DTMF frequency mapping
        self.dtmf_frequencies = {
            '1': (697, 1209), '2': (697, 1336), '3': (697, 1477), 'A': (697, 1633),
            '4': (770, 1209), '5': (770, 1336), '6': (770, 1477), 'B': (770, 1633),
            '7': (852, 1209), '8': (852, 1336), '9': (852, 1477), 'C': (852, 1633),
            '*': (941, 1209), '0': (941, 1336), '#': (941, 1477), 'D': (941, 1633)
        }
    
    def generate_dtmf_tone(self, digit: str, duration: float = 0.1, 
                          amplitude: float = 0.5) -> np.ndarray:
        """Generate DTMF tone for a specific digit."""
        if digit not in self.dtmf_frequencies:
            raise ValueError(f"Invalid DTMF digit: {digit}")
        
        low_freq, high_freq = self.dtmf_frequencies[digit]
        
        samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        
        # Generate dual-tone signal
        low_tone = amplitude * np.sin(2 * np.pi * low_freq * t)
        high_tone = amplitude * np.sin(2 * np.pi * high_freq * t)
        
        dtmf_signal = low_tone + high_tone
        return dtmf_signal.astype(np.float32)
    
    def generate_dtmf_sequence(self, digits: str, tone_duration: float = 0.1,
                              pause_duration: float = 0.05) -> np.ndarray:
        """Generate sequence of DTMF tones with pauses."""
        signal_parts = []
        
        for i, digit in enumerate(digits):
            # Add DTMF tone
            tone = self.generate_dtmf_tone(digit, tone_duration)
            signal_parts.append(tone)
            
            # Add pause between digits (except for last digit)
            if i < len(digits) - 1:
                pause_samples = int(self.sample_rate * pause_duration)
                pause = np.zeros(pause_samples, dtype=np.float32)
                signal_parts.append(pause)
        
        return np.concatenate(signal_parts)
    
    def add_noise(self, signal: np.ndarray, snr_db: float = 20) -> np.ndarray:
        """Add noise to signal with specified SNR."""
        signal_power = np.mean(signal ** 2)
        noise_power = signal_power / (10 ** (snr_db / 10))
        
        noise = np.random.normal(0, np.sqrt(noise_power), len(signal))
        return signal + noise.astype(np.float32)
    
    def add_frequency_offset(self, signal: np.ndarray, offset_hz: float) -> np.ndarray:
        """Add frequency offset to simulate oscillator drift."""
        t = np.arange(len(signal)) / self.sample_rate
        phase_shift = 2 * np.pi * offset_hz * t
        
        # Apply frequency shift
        complex_signal = signal * np.exp(1j * phase_shift)
        return np.real(complex_signal).astype(np.float32)
    
    def simulate_amplitude_distortion(self, signal: np.ndarray, 
                                    distortion_factor: float = 0.1) -> np.ndarray:
        """Simulate amplitude distortion."""
        distorted = signal * (1 + distortion_factor * np.random.random(len(signal)))
        return distorted.astype(np.float32)


class TestDTMFDetector:
    """Test suite for DTMF detector functionality."""
    
    @pytest.fixture
    def dtmf_detector(self):
        """Create DTMF detector instance."""
        return DTMFDetector(sample_rate=8000, frame_size=160)
    
    @pytest.fixture
    def signal_generator(self):
        """Create DTMF signal generator."""
        return DTMFSignalGenerator(sample_rate=8000)
    
    @pytest.mark.asyncio
    async def test_basic_dtmf_detection(self, dtmf_detector, signal_generator):
        """Test basic DTMF digit detection."""
        test_digits = "0123456789*#"
        
        for digit in test_digits:
            # Generate clean DTMF tone
            signal = signal_generator.generate_dtmf_tone(digit, duration=0.2)
            
            # Process signal in frames
            detected_digits = []
            frame_size = 160  # 20ms at 8kHz
            
            for i in range(0, len(signal) - frame_size + 1, frame_size):
                frame = signal[i:i + frame_size]
                detected = await dtmf_detector.process_frame(frame)
                if detected:
                    detected_digits.append(detected)
            
            # Should detect the digit multiple times
            assert detected_digits, f"Failed to detect digit {digit}"
            assert all(d == digit for d in detected_digits), f"Incorrect detection for {digit}"
    
    @pytest.mark.asyncio
    async def test_dtmf_sequence_detection(self, dtmf_detector, signal_generator):
        """Test detection of DTMF digit sequences."""
        test_sequence = "12345"
        signal = signal_generator.generate_dtmf_sequence(test_sequence)
        
        detected_sequence = await dtmf_detector.process_signal(signal)
        
        assert detected_sequence == test_sequence, \
            f"Expected {test_sequence}, got {detected_sequence}"
    
    @pytest.mark.asyncio
    async def test_dtmf_with_noise(self, dtmf_detector, signal_generator):
        """Test DTMF detection with background noise."""
        digit = "5"
        clean_signal = signal_generator.generate_dtmf_tone(digit, duration=0.2)
        
        # Test different noise levels
        for snr_db in [30, 20, 15, 10]:
            noisy_signal = signal_generator.add_noise(clean_signal, snr_db)
            detected = await dtmf_detector.process_signal(noisy_signal)
            
            if snr_db >= 15:  # Should work with reasonable SNR
                assert digit in detected, f"Failed to detect {digit} with {snr_db}dB SNR"
    
    @pytest.mark.asyncio
    async def test_dtmf_frequency_tolerance(self, dtmf_detector, signal_generator):
        """Test DTMF detection with frequency variations."""
        digit = "5"
        base_signal = signal_generator.generate_dtmf_tone(digit, duration=0.2)
        
        # Test small frequency offsets
        for offset_hz in [-5, -2, 0, 2, 5]:
            offset_signal = signal_generator.add_frequency_offset(base_signal, offset_hz)
            detected = await dtmf_detector.process_signal(offset_signal)
            
            assert digit in detected, f"Failed with {offset_hz}Hz offset"
    
    @pytest.mark.asyncio
    async def test_dtmf_amplitude_variations(self, dtmf_detector, signal_generator):
        """Test DTMF detection with amplitude variations."""
        digit = "8"
        
        # Test different amplitude levels
        for amplitude in [0.1, 0.3, 0.5, 0.8, 1.0]:
            signal = signal_generator.generate_dtmf_tone(digit, duration=0.2, amplitude=amplitude)
            detected = await dtmf_detector.process_signal(signal)
            
            if amplitude >= 0.1:  # Should work with reasonable amplitude
                assert digit in detected, f"Failed with amplitude {amplitude}"
    
    @pytest.mark.asyncio
    async def test_dtmf_invalid_frequencies(self, dtmf_detector, signal_generator):
        """Test rejection of invalid frequency combinations."""
        # Generate invalid frequency combinations
        invalid_freqs = [(400, 1000), (900, 1500), (1200, 1800)]
        
        for low_freq, high_freq in invalid_freqs:
            # Generate invalid dual-tone
            duration = 0.2
            samples = int(8000 * duration)
            t = np.linspace(0, duration, samples, False)
            
            invalid_signal = 0.5 * (np.sin(2 * np.pi * low_freq * t) + 
                                   np.sin(2 * np.pi * high_freq * t))
            
            detected = await dtmf_detector.process_signal(invalid_signal.astype(np.float32))
            
            # Should not detect any valid DTMF digits
            assert not detected, f"Incorrectly detected DTMF in invalid signal {low_freq}/{high_freq}"
    
    @pytest.mark.asyncio
    async def test_dtmf_timing_requirements(self, dtmf_detector, signal_generator):
        """Test DTMF minimum duration requirements."""
        digit = "7"
        
        # Test various durations
        durations = [0.02, 0.04, 0.06, 0.08, 0.1, 0.15, 0.2]  # 20ms to 200ms
        
        for duration in durations:
            signal = signal_generator.generate_dtmf_tone(digit, duration)
            detected = await dtmf_detector.process_signal(signal)
            
            if duration >= 0.04:  # Minimum 40ms duration
                assert digit in detected, f"Failed to detect {digit} with {duration*1000}ms duration"
            else:
                # Very short tones might not be detected
                pass  # Allow either detection or non-detection
    
    @pytest.mark.asyncio
    async def test_dtmf_concurrent_processing(self, dtmf_detector, signal_generator):
        """Test concurrent DTMF processing."""
        # Generate multiple signals
        signals = []
        expected_digits = []
        
        for digit in "123":
            signal = signal_generator.generate_dtmf_tone(digit, duration=0.15)
            signals.append(signal)
            expected_digits.append(digit)
        
        # Process signals concurrently
        tasks = [dtmf_detector.process_signal(signal) for signal in signals]
        results = await asyncio.gather(*tasks)
        
        # Verify all digits were detected
        for i, result in enumerate(results):
            assert expected_digits[i] in result, \
                f"Failed concurrent detection of {expected_digits[i]}"


class TestDTMFProcessor:
    """Test suite for DTMF processor functionality."""
    
    @pytest.fixture
    def dtmf_processor(self):
        """Create DTMF processor instance."""
        processor = DTMFProcessor()
        return processor
    
    @pytest.fixture
    def mock_call_session(self):
        """Create mock call session."""
        session = MagicMock()
        session.call_id = "test-call-123"
        session.caller.number = "+1234567890"
        session.callee.number = "+0987654321"
        return session
    
    @pytest.mark.asyncio
    async def test_dtmf_event_generation(self, dtmf_processor, mock_call_session):
        """Test DTMF event generation."""
        digit = "5"
        timestamp = time.time()
        
        # Process DTMF event
        event = await dtmf_processor.process_dtmf_event(
            call_session=mock_call_session,
            digit=digit,
            timestamp=timestamp
        )
        
        assert event is not None
        assert event["type"] == "dtmf"
        assert event["digit"] == digit
        assert event["call_id"] == mock_call_session.call_id
        assert event["timestamp"] == timestamp
    
    @pytest.mark.asyncio
    async def test_dtmf_sequence_processing(self, dtmf_processor, mock_call_session):
        """Test processing of DTMF digit sequences."""
        sequence = "12345"
        
        events = []
        for digit in sequence:
            event = await dtmf_processor.process_dtmf_event(
                call_session=mock_call_session,
                digit=digit,
                timestamp=time.time()
            )
            events.append(event)
        
        # Get processed sequence
        processed_sequence = dtmf_processor.get_digit_sequence(mock_call_session.call_id)
        
        assert processed_sequence == sequence
        assert len(events) == len(sequence)
    
    @pytest.mark.asyncio
    async def test_dtmf_debouncing(self, dtmf_processor, mock_call_session):
        """Test DTMF digit debouncing."""
        digit = "3"
        base_time = time.time()
        
        # Send same digit multiple times quickly
        events = []
        for i in range(5):
            event = await dtmf_processor.process_dtmf_event(
                call_session=mock_call_session,
                digit=digit,
                timestamp=base_time + i * 0.01  # 10ms apart
            )
            if event:
                events.append(event)
        
        # Should only generate one event due to debouncing
        assert len(events) == 1
        assert events[0]["digit"] == digit
    
    @pytest.mark.asyncio
    async def test_dtmf_timeout_handling(self, dtmf_processor, mock_call_session):
        """Test DTMF sequence timeout handling."""
        # Configure short timeout for testing
        dtmf_processor.sequence_timeout = 2.0  # 2 seconds
        
        # Send first digit
        await dtmf_processor.process_dtmf_event(
            call_session=mock_call_session,
            digit="1",
            timestamp=time.time()
        )
        
        # Wait for timeout
        await asyncio.sleep(2.5)
        
        # Send second digit after timeout
        await dtmf_processor.process_dtmf_event(
            call_session=mock_call_session,
            digit="2",
            timestamp=time.time()
        )
        
        # Should only have the second digit
        sequence = dtmf_processor.get_digit_sequence(mock_call_session.call_id)
        assert sequence == "2"
    
    @pytest.mark.asyncio
    async def test_dtmf_callback_integration(self, dtmf_processor, mock_call_session):
        """Test DTMF callback integration."""
        callback_events = []
        
        async def test_callback(event):
            callback_events.append(event)
        
        # Register callback
        dtmf_processor.register_callback(test_callback)
        
        # Process DTMF events
        digits = "456"
        for digit in digits:
            await dtmf_processor.process_dtmf_event(
                call_session=mock_call_session,
                digit=digit,
                timestamp=time.time()
            )
        
        # Verify callbacks were called
        assert len(callback_events) == len(digits)
        for i, event in enumerate(callback_events):
            assert event["digit"] == digits[i]


class TestIVRManager:
    """Test suite for IVR manager functionality."""
    
    @pytest.fixture
    def ivr_manager(self):
        """Create IVR manager instance."""
        return IVRManager()
    
    @pytest.fixture
    def sample_ivr_menu(self):
        """Create sample IVR menu configuration."""
        return {
            "main_menu": {
                "prompt": "Welcome! Press 1 for Sales, 2 for Support, 9 for Directory",
                "options": {
                    "1": {"action": "transfer", "target": "+15551234567", "prompt": "Connecting to Sales"},
                    "2": {"action": "submenu", "target": "support_menu"},
                    "9": {"action": "directory"},
                    "*": {"action": "repeat"},
                    "0": {"action": "operator"}
                },
                "timeout": 5,
                "max_retries": 3
            },
            "support_menu": {
                "prompt": "Support Menu: Press 1 for Technical, 2 for Billing",
                "options": {
                    "1": {"action": "transfer", "target": "+15551234568"},
                    "2": {"action": "transfer", "target": "+15551234569"},
                    "*": {"action": "previous_menu"},
                    "#": {"action": "main_menu"}
                },
                "timeout": 3,
                "max_retries": 2
            }
        }
    
    @pytest.mark.asyncio
    async def test_ivr_menu_loading(self, ivr_manager, sample_ivr_menu):
        """Test IVR menu configuration loading."""
        await ivr_manager.load_menu_config(sample_ivr_menu)
        
        assert "main_menu" in ivr_manager.menus
        assert "support_menu" in ivr_manager.menus
        
        main_menu = ivr_manager.menus["main_menu"]
        assert main_menu["timeout"] == 5
        assert "1" in main_menu["options"]
    
    @pytest.mark.asyncio
    async def test_ivr_session_start(self, ivr_manager, sample_ivr_menu):
        """Test IVR session initialization."""
        await ivr_manager.load_menu_config(sample_ivr_menu)
        
        call_id = "test-call-ivr-001"
        session = await ivr_manager.start_session(call_id, "main_menu")
        
        assert session is not None
        assert session["call_id"] == call_id
        assert session["current_menu"] == "main_menu"
        assert session["retry_count"] == 0
    
    @pytest.mark.asyncio
    async def test_ivr_digit_processing(self, ivr_manager, sample_ivr_menu):
        """Test IVR digit processing and navigation."""
        await ivr_manager.load_menu_config(sample_ivr_menu)
        call_id = "test-call-ivr-002"
        
        # Start session
        await ivr_manager.start_session(call_id, "main_menu")
        
        # Process digit "2" (should go to support_menu)
        result = await ivr_manager.process_digit(call_id, "2")
        
        assert result["action"] == "submenu"
        assert result["next_menu"] == "support_menu"
        
        # Process digit "1" in support menu (should transfer)
        result = await ivr_manager.process_digit(call_id, "1")
        
        assert result["action"] == "transfer"
        assert result["target"] == "+15551234568"
    
    @pytest.mark.asyncio
    async def test_ivr_timeout_handling(self, ivr_manager, sample_ivr_menu):
        """Test IVR timeout and retry logic."""
        await ivr_manager.load_menu_config(sample_ivr_menu)
        call_id = "test-call-ivr-003"
        
        # Start session
        await ivr_manager.start_session(call_id, "main_menu")
        
        # Simulate timeout
        result = await ivr_manager.handle_timeout(call_id)
        
        assert result["action"] == "repeat"
        
        # Get session and check retry count
        session = ivr_manager.get_session(call_id)
        assert session["retry_count"] == 1
    
    @pytest.mark.asyncio
    async def test_ivr_max_retries(self, ivr_manager, sample_ivr_menu):
        """Test IVR maximum retries handling."""
        await ivr_manager.load_menu_config(sample_ivr_menu)
        call_id = "test-call-ivr-004"
        
        # Start session
        await ivr_manager.start_session(call_id, "main_menu")
        
        # Exceed max retries
        for _ in range(4):  # max_retries is 3
            await ivr_manager.handle_timeout(call_id)
        
        session = ivr_manager.get_session(call_id)
        result = await ivr_manager.handle_timeout(call_id)
        
        assert result["action"] == "hangup"
    
    @pytest.mark.asyncio
    async def test_ivr_invalid_digit(self, ivr_manager, sample_ivr_menu):
        """Test IVR invalid digit handling."""
        await ivr_manager.load_menu_config(sample_ivr_menu)
        call_id = "test-call-ivr-005"
        
        # Start session
        await ivr_manager.start_session(call_id, "main_menu")
        
        # Process invalid digit
        result = await ivr_manager.process_digit(call_id, "7")  # Not in menu
        
        assert result["action"] == "invalid"
        assert "error" in result


class TestMusicOnHold:
    """Test suite for Music on Hold functionality."""
    
    @pytest.fixture
    def music_on_hold(self):
        """Create Music on Hold instance."""
        return MusicOnHold()
    
    @pytest.fixture
    def sample_audio_file(self, tmp_path):
        """Create sample audio file for testing."""
        # Generate simple sine wave audio file
        sample_rate = 8000
        duration = 2.0  # 2 seconds
        frequency = 440  # 440 Hz
        
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        audio_data = 0.5 * np.sin(2 * np.pi * frequency * t)
        
        # Convert to 16-bit integers
        audio_16bit = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file
        audio_file = tmp_path / "test_music.wav"
        
        import wave
        with wave.open(str(audio_file), 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_16bit.tobytes())
        
        return str(audio_file)
    
    @pytest.mark.asyncio
    async def test_music_loading(self, music_on_hold, sample_audio_file):
        """Test music file loading."""
        success = await music_on_hold.load_music_file(sample_audio_file)
        
        assert success is True
        assert music_on_hold.is_loaded() is True
        assert music_on_hold.get_duration() > 0
    
    @pytest.mark.asyncio
    async def test_music_playback_start_stop(self, music_on_hold, sample_audio_file):
        """Test music playback start and stop."""
        await music_on_hold.load_music_file(sample_audio_file)
        
        call_id = "test-call-moh-001"
        
        # Start playback
        success = await music_on_hold.start_playback(call_id)
        assert success is True
        assert music_on_hold.is_playing(call_id) is True
        
        # Stop playback
        await music_on_hold.stop_playback(call_id)
        assert music_on_hold.is_playing(call_id) is False
    
    @pytest.mark.asyncio
    async def test_music_frame_generation(self, music_on_hold, sample_audio_file):
        """Test audio frame generation for streaming."""
        await music_on_hold.load_music_file(sample_audio_file)
        
        call_id = "test-call-moh-002"
        await music_on_hold.start_playback(call_id)
        
        # Get audio frames
        frame_size = 160  # 20ms at 8kHz
        frames = []
        
        for _ in range(10):  # Get 10 frames
            frame = await music_on_hold.get_audio_frame(call_id, frame_size)
            assert frame is not None
            assert len(frame) == frame_size
            frames.append(frame)
        
        # Frames should not be identical (music is playing)
        assert not all(np.array_equal(frames[0], frame) for frame in frames[1:])
    
    @pytest.mark.asyncio
    async def test_music_looping(self, music_on_hold, sample_audio_file):
        """Test music looping functionality."""
        await music_on_hold.load_music_file(sample_audio_file)
        
        call_id = "test-call-moh-003"
        await music_on_hold.start_playback(call_id, loop=True)
        
        # Get more frames than the file duration
        duration = music_on_hold.get_duration()
        frames_needed = int((duration + 1.0) * 8000 / 160)  # Extra second
        
        frames = []
        for _ in range(frames_needed):
            frame = await music_on_hold.get_audio_frame(call_id, 160)
            if frame is not None:
                frames.append(frame)
        
        # Should have gotten frames beyond the original file duration
        assert len(frames) > duration * 8000 / 160
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_playbacks(self, music_on_hold, sample_audio_file):
        """Test multiple concurrent music playbacks."""
        await music_on_hold.load_music_file(sample_audio_file)
        
        call_ids = ["moh-call-1", "moh-call-2", "moh-call-3"]
        
        # Start playback for all calls
        for call_id in call_ids:
            success = await music_on_hold.start_playback(call_id)
            assert success is True
        
        # Verify all are playing
        for call_id in call_ids:
            assert music_on_hold.is_playing(call_id) is True
        
        # Get frames for each call
        for call_id in call_ids:
            frame = await music_on_hold.get_audio_frame(call_id, 160)
            assert frame is not None
        
        # Stop all playbacks
        for call_id in call_ids:
            await music_on_hold.stop_playback(call_id)
            assert music_on_hold.is_playing(call_id) is False


class TestDTMFIntegration:
    """Integration tests for DTMF system components."""
    
    @pytest.fixture
    def dtmf_system(self):
        """Create integrated DTMF system."""
        detector = DTMFDetector()
        processor = DTMFProcessor()
        ivr_manager = IVRManager()
        music_on_hold = MusicOnHold()
        
        return {
            'detector': detector,
            'processor': processor,
            'ivr': ivr_manager,
            'moh': music_on_hold
        }
    
    @pytest.fixture
    def mock_call_manager(self):
        """Create mock call manager."""
        call_manager = AsyncMock()
        call_manager.transfer_call = AsyncMock(return_value=True)
        call_manager.hangup_call = AsyncMock(return_value=True)
        return call_manager
    
    @pytest.mark.asyncio
    async def test_end_to_end_dtmf_ivr_flow(self, dtmf_system, mock_call_manager):
        """Test complete DTMF to IVR flow."""
        detector = dtmf_system['detector']
        processor = dtmf_system['processor']
        ivr = dtmf_system['ivr']
        
        # Setup IVR menu
        menu_config = {
            "main_menu": {
                "prompt": "Press 1 for Sales, 2 for Support",
                "options": {
                    "1": {"action": "transfer", "target": "+15551111111"},
                    "2": {"action": "transfer", "target": "+15552222222"}
                },
                "timeout": 5,
                "max_retries": 3
            }
        }
        
        await ivr.load_menu_config(menu_config)
        
        call_id = "test-integration-001"
        
        # Start IVR session
        await ivr.start_session(call_id, "main_menu")
        
        # Simulate DTMF detection and processing
        signal_gen = DTMFSignalGenerator()
        dtmf_signal = signal_gen.generate_dtmf_tone("1", duration=0.15)
        
        # Detect DTMF
        detected_digit = await detector.process_signal(dtmf_signal)
        assert "1" in detected_digit
        
        # Process through IVR
        result = await ivr.process_digit(call_id, "1")
        
        assert result["action"] == "transfer"
        assert result["target"] == "+15551111111"
    
    @pytest.mark.asyncio
    async def test_dtmf_processor_ivr_integration(self, dtmf_system):
        """Test DTMF processor integration with IVR."""
        processor = dtmf_system['processor']
        ivr = dtmf_system['ivr']
        
        # Setup callback integration
        async def ivr_callback(dtmf_event):
            call_id = dtmf_event["call_id"]
            digit = dtmf_event["digit"]
            
            # Forward to IVR
            result = await ivr.process_digit(call_id, digit)
            return result
        
        processor.register_callback(ivr_callback)
        
        # Setup simple IVR
        menu_config = {
            "test_menu": {
                "prompt": "Press any digit",
                "options": {
                    "5": {"action": "transfer", "target": "+15555555555"}
                },
                "timeout": 5,
                "max_retries": 1
            }
        }
        
        await ivr.load_menu_config(menu_config)
        call_id = "test-integration-002"
        await ivr.start_session(call_id, "test_menu")
        
        # Create mock call session
        mock_session = MagicMock()
        mock_session.call_id = call_id
        
        # Process DTMF through processor
        await processor.process_dtmf_event(
            call_session=mock_session,
            digit="5",
            timestamp=time.time()
        )
        
        # Verify IVR processed the digit
        session = ivr.get_session(call_id)
        assert session is not None


# Performance and stress tests
class TestDTMFPerformance:
    """Performance tests for DTMF functionality."""
    
    @pytest.mark.asyncio
    async def test_dtmf_detection_performance(self):
        """Test DTMF detection performance under load."""
        detector = DTMFDetector()
        signal_gen = DTMFSignalGenerator()
        
        # Generate test signals
        test_signals = []
        for digit in "0123456789*#":
            signal = signal_gen.generate_dtmf_tone(digit, duration=0.1)
            test_signals.append((digit, signal))
        
        # Measure processing time
        start_time = time.time()
        
        for _ in range(100):  # Process each signal 100 times
            for digit, signal in test_signals:
                detected = await detector.process_signal(signal)
                assert digit in detected
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process 1200 signals (12 digits × 100 iterations) reasonably fast
        signals_per_second = 1200 / processing_time
        
        print(f"DTMF Detection Performance: {signals_per_second:.1f} signals/second")
        assert signals_per_second > 100, "DTMF detection too slow"
    
    @pytest.mark.asyncio
    async def test_concurrent_dtmf_processing(self):
        """Test concurrent DTMF processing performance."""
        processor = DTMFProcessor()
        
        # Create multiple mock call sessions
        mock_sessions = []
        for i in range(50):
            session = MagicMock()
            session.call_id = f"perf-test-{i}"
            mock_sessions.append(session)
        
        # Process DTMF events concurrently
        async def process_dtmf_sequence(session):
            for digit in "123456789":
                await processor.process_dtmf_event(
                    call_session=session,
                    digit=digit,
                    timestamp=time.time()
                )
        
        start_time = time.time()
        
        # Process all sessions concurrently
        tasks = [process_dtmf_sequence(session) for session in mock_sessions]
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"Concurrent DTMF Processing: {len(mock_sessions)} calls in {processing_time:.2f}s")
        assert processing_time < 5.0, "Concurrent processing too slow"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
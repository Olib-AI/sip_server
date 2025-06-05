"""
Comprehensive unit tests for Audio Processing components.
Tests codec conversion, RTP handling, and audio quality validation.
"""
import pytest
import numpy as np
import struct
import time
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from src.audio.codecs import AudioProcessor
from src.audio.rtp import RTPManager, RTPSession, RTPStatistics


class TestAudioProcessor:
    """Test AudioProcessor codec conversion functionality."""
    
    @pytest.fixture
    def audio_processor(self):
        """Create test audio processor."""
        return AudioProcessor()
    
    def test_audio_processor_initialization(self, audio_processor):
        """Test audio processor initialization."""
        assert audio_processor.sample_rate == 8000
        assert audio_processor.frame_size == 160
        assert hasattr(audio_processor, 'pcmu_table')
        assert hasattr(audio_processor, 'pcma_table')
    
    def test_pcm_to_pcmu_conversion(self, audio_processor, sample_audio_data):
        """Test PCM to PCMU (μ-law) conversion."""
        pcm_data = sample_audio_data["pcm"]
        
        # Convert PCM to PCMU
        pcmu_data = audio_processor.pcm_to_pcmu(pcm_data)
        
        assert len(pcmu_data) == len(pcm_data) // 2  # 16-bit to 8-bit
        assert isinstance(pcmu_data, bytes)
        
        # Verify conversion produces valid μ-law data
        assert len(pcmu_data) > 0
        assert not all(b == 0 for b in pcmu_data)  # Should not be all silence
    
    def test_pcmu_to_pcm_conversion(self, audio_processor, sample_audio_data):
        """Test PCMU (μ-law) to PCM conversion."""
        pcmu_data = sample_audio_data["pcmu"]
        
        # Convert PCMU to PCM
        pcm_data = audio_processor.pcmu_to_pcm(pcmu_data)
        
        assert len(pcm_data) == len(pcmu_data) * 2  # 8-bit to 16-bit
        assert isinstance(pcm_data, bytes)
        
        # Verify conversion produces valid PCM data
        assert len(pcm_data) > 0
    
    def test_pcm_to_pcma_conversion(self, audio_processor, sample_audio_data):
        """Test PCM to PCMA (A-law) conversion."""
        pcm_data = sample_audio_data["pcm"]
        
        # Convert PCM to PCMA
        pcma_data = audio_processor.pcm_to_pcma(pcm_data)
        
        assert len(pcma_data) == len(pcm_data) // 2  # 16-bit to 8-bit
        assert isinstance(pcma_data, bytes)
        
        # Verify conversion produces valid A-law data
        assert len(pcma_data) > 0
        assert not all(b == 0 for b in pcma_data)  # Should not be all silence
    
    def test_pcma_to_pcm_conversion(self, audio_processor, sample_audio_data):
        """Test PCMA (A-law) to PCM conversion."""
        pcma_data = sample_audio_data["pcma"]
        
        # Convert PCMA to PCM
        pcm_data = audio_processor.pcma_to_pcm(pcma_data)
        
        assert len(pcm_data) == len(pcma_data) * 2  # 8-bit to 16-bit
        assert isinstance(pcm_data, bytes)
        
        # Verify conversion produces valid PCM data
        assert len(pcm_data) > 0
    
    def test_roundtrip_conversion_pcmu(self, audio_processor, sample_audio_data):
        """Test PCM -> PCMU -> PCM roundtrip conversion."""
        original_pcm = sample_audio_data["pcm"]
        
        # Convert PCM -> PCMU -> PCM
        pcmu_data = audio_processor.pcm_to_pcmu(original_pcm)
        recovered_pcm = audio_processor.pcmu_to_pcm(pcmu_data)
        
        assert len(recovered_pcm) == len(original_pcm)
        
        # μ-law is lossy, so we check for reasonable similarity
        original_samples = np.frombuffer(original_pcm, dtype=np.int16)
        recovered_samples = np.frombuffer(recovered_pcm, dtype=np.int16)
        
        # Calculate correlation coefficient
        correlation = np.corrcoef(original_samples, recovered_samples)[0, 1]
        assert correlation > 0.8  # Should be reasonably similar
    
    def test_roundtrip_conversion_pcma(self, audio_processor, sample_audio_data):
        """Test PCM -> PCMA -> PCM roundtrip conversion."""
        original_pcm = sample_audio_data["pcm"]
        
        # Convert PCM -> PCMA -> PCM
        pcma_data = audio_processor.pcm_to_pcma(original_pcm)
        recovered_pcm = audio_processor.pcma_to_pcm(pcma_data)
        
        assert len(recovered_pcm) == len(original_pcm)
        
        # A-law is lossy, so we check for reasonable similarity
        original_samples = np.frombuffer(original_pcm, dtype=np.int16)
        recovered_samples = np.frombuffer(recovered_pcm, dtype=np.int16)
        
        # Calculate correlation coefficient
        correlation = np.corrcoef(original_samples, recovered_samples)[0, 1]
        assert correlation > 0.8  # Should be reasonably similar
    
    def test_audio_resampling(self, audio_processor):
        """Test audio resampling functionality."""
        # Create 16kHz audio data
        sample_rate_16k = 16000
        duration = 0.02  # 20ms
        samples_16k = int(sample_rate_16k * duration)
        
        # Generate sine wave
        t = np.linspace(0, duration, samples_16k, False)
        sine_wave = np.sin(2 * np.pi * 1000 * t)
        audio_16k = (sine_wave * 32767).astype(np.int16).tobytes()
        
        # Resample to 8kHz
        audio_8k = audio_processor.resample_audio(audio_16k, sample_rate_16k, 8000)
        
        # Should have half the samples
        expected_samples_8k = samples_16k // 2
        assert len(audio_8k) == expected_samples_8k * 2  # 2 bytes per sample
    
    def test_audio_mixing(self, audio_processor, sample_audio_data):
        """Test audio mixing functionality."""
        audio1 = sample_audio_data["pcm"]
        audio2 = sample_audio_data["pcm"]
        
        # Mix two audio streams
        mixed_audio = audio_processor.mix_audio([audio1, audio2])
        
        assert len(mixed_audio) == len(audio1)
        assert isinstance(mixed_audio, bytes)
        
        # Mixed audio should not be identical to either input
        assert mixed_audio != audio1
        assert mixed_audio != audio2
    
    def test_audio_normalization(self, audio_processor):
        """Test audio level normalization."""
        # Create audio with varying levels
        samples = 160
        loud_audio = (np.ones(samples) * 20000).astype(np.int16).tobytes()
        quiet_audio = (np.ones(samples) * 1000).astype(np.int16).tobytes()
        
        # Normalize audio levels
        normalized_loud = audio_processor.normalize_audio(loud_audio, target_level=0.5)
        normalized_quiet = audio_processor.normalize_audio(quiet_audio, target_level=0.5)
        
        # Both should be normalized to similar levels
        loud_samples = np.frombuffer(normalized_loud, dtype=np.int16)
        quiet_samples = np.frombuffer(normalized_quiet, dtype=np.int16)
        
        loud_rms = np.sqrt(np.mean(loud_samples.astype(float) ** 2))
        quiet_rms = np.sqrt(np.mean(quiet_samples.astype(float) ** 2))
        
        # RMS levels should be closer after normalization
        ratio = max(loud_rms, quiet_rms) / min(loud_rms, quiet_rms)
        assert ratio < 2.0  # Should be within 2x of each other
    
    def test_audio_silence_detection(self, audio_processor):
        """Test silence detection functionality."""
        # Create silent audio
        silent_audio = (np.zeros(160)).astype(np.int16).tobytes()
        
        # Create audio with signal
        signal_audio = (np.sin(np.linspace(0, 2*np.pi, 160)) * 1000).astype(np.int16).tobytes()
        
        # Test silence detection
        assert audio_processor.is_silence(silent_audio) is True
        assert audio_processor.is_silence(signal_audio) is False
    
    def test_audio_gain_control(self, audio_processor, sample_audio_data):
        """Test automatic gain control."""
        audio_data = sample_audio_data["pcm"]
        
        # Apply gain control
        gained_audio = audio_processor.apply_gain(audio_data, gain_db=6.0)
        
        assert len(gained_audio) == len(audio_data)
        
        # Verify gain was applied
        original_samples = np.frombuffer(audio_data, dtype=np.int16)
        gained_samples = np.frombuffer(gained_audio, dtype=np.int16)
        
        # Gained audio should have higher amplitude
        original_rms = np.sqrt(np.mean(original_samples.astype(float) ** 2))
        gained_rms = np.sqrt(np.mean(gained_samples.astype(float) ** 2))
        
        assert gained_rms > original_rms
    
    def test_codec_tables_integrity(self, audio_processor):
        """Test codec lookup tables integrity."""
        # Verify μ-law table
        assert len(audio_processor.pcmu_table) == 65536  # 16-bit input range
        assert all(0 <= val <= 255 for val in audio_processor.pcmu_table)
        
        # Verify A-law table
        assert len(audio_processor.pcma_table) == 65536  # 16-bit input range
        assert all(0 <= val <= 255 for val in audio_processor.pcma_table)
        
        # Test specific values
        assert audio_processor.pcmu_table[0] == 255  # Zero maps to 255 in μ-law
        assert audio_processor.pcma_table[0] == 213  # Zero maps to 213 in A-law
    
    def test_invalid_input_handling(self, audio_processor):
        """Test handling of invalid input data."""
        # Test with empty data
        with pytest.raises((ValueError, IndexError)):
            audio_processor.pcm_to_pcmu(b"")
        
        # Test with odd-length data (invalid for 16-bit PCM)
        with pytest.raises((ValueError, struct.error)):
            audio_processor.pcm_to_pcmu(b"\\x00\\x01\\x02")  # 3 bytes
        
        # Test with None input
        with pytest.raises((TypeError, AttributeError)):
            audio_processor.pcm_to_pcmu(None)
    
    def test_performance_benchmarks(self, audio_processor, sample_audio_data, performance_thresholds):
        """Test codec conversion performance."""
        pcm_data = sample_audio_data["pcm"]
        
        # Benchmark PCMU conversion
        start_time = time.perf_counter()
        for _ in range(1000):  # Convert 1000 frames
            audio_processor.pcm_to_pcmu(pcm_data)
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) / 1000) * 1000
        assert avg_time_ms < performance_thresholds["codec_conversion_ms"]
        
        # Benchmark PCMA conversion
        start_time = time.perf_counter()
        for _ in range(1000):  # Convert 1000 frames
            audio_processor.pcm_to_pcma(pcm_data)
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) / 1000) * 1000
        assert avg_time_ms < performance_thresholds["codec_conversion_ms"]


class TestRTPSession:
    """Test RTP session functionality."""
    
    @pytest.fixture
    def rtp_session(self):
        """Create test RTP session."""
        return RTPSession(
            session_id="test-session",
            local_port=10000,
            remote_host="192.168.1.100",
            remote_port=5004
        )
    
    def test_rtp_session_creation(self, rtp_session):
        """Test RTP session creation."""
        assert rtp_session.session_id == "test-session"
        assert rtp_session.local_port == 10000
        assert rtp_session.remote_host == "192.168.1.100"
        assert rtp_session.remote_port == 5004
        assert rtp_session.sequence_number == 0
        assert rtp_session.ssrc != 0
    
    @pytest.mark.asyncio
    async def test_rtp_packet_creation(self, rtp_session, sample_audio_data):
        """Test RTP packet creation."""
        payload = sample_audio_data["pcmu"]
        payload_type = 0  # PCMU
        
        packet = rtp_session.create_rtp_packet(payload, payload_type)
        
        # Verify RTP header (12 bytes minimum)
        assert len(packet) >= 12 + len(payload)
        
        # Parse header
        header = packet[:12]
        version = (header[0] >> 6) & 0x3
        payload_type_from_header = header[1] & 0x7F
        seq_num = struct.unpack('>H', header[2:4])[0]
        timestamp = struct.unpack('>I', header[4:8])[0]
        ssrc = struct.unpack('>I', header[8:12])[0]
        
        assert version == 2
        assert payload_type_from_header == payload_type
        assert seq_num == rtp_session.sequence_number
        assert ssrc == rtp_session.ssrc
        
        # Verify payload
        packet_payload = packet[12:]
        assert packet_payload == payload
    
    @pytest.mark.asyncio
    async def test_rtp_packet_sending(self, rtp_session, sample_rtp_packet):
        """Test RTP packet sending."""
        # Mock socket
        with patch('asyncio.DatagramProtocol') as mock_protocol:
            mock_transport = MagicMock()
            rtp_session.transport = mock_transport
            
            await rtp_session.send_packet(sample_rtp_packet)
            
            # Verify packet was sent
            mock_transport.sendto.assert_called_once_with(
                sample_rtp_packet,
                (rtp_session.remote_host, rtp_session.remote_port)
            )
    
    def test_rtp_packet_parsing(self, rtp_session, sample_rtp_packet):
        """Test RTP packet parsing."""
        parsed = rtp_session.parse_rtp_packet(sample_rtp_packet)
        
        assert 'version' in parsed
        assert 'payload_type' in parsed
        assert 'sequence_number' in parsed
        assert 'timestamp' in parsed
        assert 'ssrc' in parsed
        assert 'payload' in parsed
        
        assert parsed['version'] == 2
        assert parsed['payload_type'] == 0  # PCMU
        assert len(parsed['payload']) > 0
    
    def test_sequence_number_increment(self, rtp_session):
        """Test sequence number increment."""
        initial_seq = rtp_session.sequence_number
        
        # Create multiple packets
        for i in range(5):
            payload = b'test_payload_' + str(i).encode()
            rtp_session.create_rtp_packet(payload, 0)
        
        # Sequence number should have incremented
        assert rtp_session.sequence_number == initial_seq + 5
    
    def test_sequence_number_wraparound(self, rtp_session):
        """Test sequence number wraparound at 65535."""
        # Set sequence number near maximum
        rtp_session.sequence_number = 65534
        
        # Create packets to trigger wraparound
        payload = b'test_payload'
        rtp_session.create_rtp_packet(payload, 0)  # seq = 65535
        rtp_session.create_rtp_packet(payload, 0)  # seq = 0 (wrapped)
        
        assert rtp_session.sequence_number == 0
    
    def test_timestamp_calculation(self, rtp_session):
        """Test RTP timestamp calculation."""
        sample_rate = 8000
        frame_duration_ms = 20
        
        timestamp1 = rtp_session.calculate_timestamp(sample_rate, frame_duration_ms)
        timestamp2 = rtp_session.calculate_timestamp(sample_rate, frame_duration_ms)
        
        # Timestamps should increment by sample_rate * duration
        expected_increment = sample_rate * frame_duration_ms // 1000
        assert timestamp2 - timestamp1 == expected_increment


class TestRTPStatistics:
    """Test RTP statistics tracking."""
    
    @pytest.fixture
    def rtp_stats(self):
        """Create test RTP statistics."""
        return RTPStatistics()
    
    def test_statistics_initialization(self, rtp_stats):
        """Test statistics initialization."""
        assert rtp_stats.packets_sent == 0
        assert rtp_stats.packets_received == 0
        assert rtp_stats.bytes_sent == 0
        assert rtp_stats.bytes_received == 0
        assert rtp_stats.packets_lost == 0
        assert rtp_stats.jitter_ms == 0.0
        assert rtp_stats.start_time > 0
    
    def test_packet_tracking(self, rtp_stats):
        """Test packet tracking functionality."""
        # Track sent packets
        rtp_stats.record_sent_packet(160)  # 160 bytes payload
        rtp_stats.record_sent_packet(160)
        
        assert rtp_stats.packets_sent == 2
        assert rtp_stats.bytes_sent == 320
        
        # Track received packets
        rtp_stats.record_received_packet(160)
        
        assert rtp_stats.packets_received == 1
        assert rtp_stats.bytes_received == 160
    
    def test_packet_loss_calculation(self, rtp_stats):
        """Test packet loss rate calculation."""
        # Send 100 packets, receive 95
        for _ in range(100):
            rtp_stats.record_sent_packet(160)
        
        for _ in range(95):
            rtp_stats.record_received_packet(160)
        
        loss_rate = rtp_stats.packet_loss_rate()
        assert abs(loss_rate - 0.05) < 0.001  # 5% loss rate
    
    def test_jitter_calculation(self, rtp_stats):
        """Test jitter calculation."""
        # Simulate varying packet arrival times
        arrival_times = [0, 20.5, 40.2, 61.8, 79.5]  # ms
        
        for i, arrival_time in enumerate(arrival_times):
            rtp_stats.record_packet_arrival(i * 20, arrival_time)  # Expected every 20ms
        
        # Jitter should be calculated
        assert rtp_stats.jitter_ms > 0
        assert rtp_stats.jitter_ms < 10  # Should be reasonable
    
    def test_bitrate_calculation(self, rtp_stats):
        """Test bitrate calculation."""
        # Simulate 1 second of data at 64kbps (8000 bytes)
        import time
        
        start_time = time.time()
        rtp_stats.start_time = start_time
        
        # Send data over time
        for i in range(50):  # 50 packets of 160 bytes each
            rtp_stats.record_sent_packet(160)
            time.sleep(0.02)  # 20ms intervals
        
        bitrate = rtp_stats.calculate_bitrate()
        
        # Should be approximately 64 kbps (160 bytes * 50 packets * 8 bits/byte)
        expected_bitrate = (160 * 50 * 8) / (time.time() - start_time)
        assert abs(bitrate - expected_bitrate) < expected_bitrate * 0.1  # Within 10%
    
    def test_statistics_reset(self, rtp_stats):
        """Test statistics reset functionality."""
        # Add some data
        rtp_stats.record_sent_packet(160)
        rtp_stats.record_received_packet(160)
        rtp_stats.packets_lost = 5
        
        # Reset statistics
        rtp_stats.reset()
        
        assert rtp_stats.packets_sent == 0
        assert rtp_stats.packets_received == 0
        assert rtp_stats.bytes_sent == 0
        assert rtp_stats.bytes_received == 0
        assert rtp_stats.packets_lost == 0
        assert rtp_stats.jitter_ms == 0.0


class TestRTPManager:
    """Test RTP manager functionality."""
    
    @pytest.mark.asyncio
    async def test_rtp_manager_initialization(self, rtp_manager):
        """Test RTP manager initialization."""
        assert rtp_manager.port_range == (10000, 11000)
        assert len(rtp_manager.active_sessions) == 0
        assert len(rtp_manager.port_allocations) == 0
    
    @pytest.mark.asyncio
    async def test_session_creation(self, rtp_manager):
        """Test RTP session creation."""
        session = await rtp_manager.create_session(
            local_port=10000,
            remote_host="192.168.1.100",
            remote_port=5004
        )
        
        assert session is not None
        assert session.local_port == 10000
        assert session.remote_host == "192.168.1.100"
        assert session.remote_port == 5004
        assert session.session_id in rtp_manager.active_sessions
    
    @pytest.mark.asyncio
    async def test_automatic_port_allocation(self, rtp_manager):
        """Test automatic port allocation."""
        session = await rtp_manager.create_session(
            remote_host="192.168.1.100",
            remote_port=5004
        )
        
        assert session is not None
        assert rtp_manager.port_range[0] <= session.local_port <= rtp_manager.port_range[1]
        assert session.local_port in rtp_manager.port_allocations
    
    @pytest.mark.asyncio
    async def test_port_conflict_resolution(self, rtp_manager):
        """Test port conflict resolution."""
        # Create session with specific port
        session1 = await rtp_manager.create_session(
            local_port=10000,
            remote_host="192.168.1.100",
            remote_port=5004
        )
        
        # Try to create another session with same port
        session2 = await rtp_manager.create_session(
            local_port=10000,  # Same port
            remote_host="192.168.1.101",
            remote_port=5004
        )
        
        # Should allocate different port for second session
        assert session1.local_port != session2.local_port
    
    @pytest.mark.asyncio
    async def test_session_cleanup(self, rtp_manager):
        """Test session cleanup."""
        session = await rtp_manager.create_session(
            local_port=10000,
            remote_host="192.168.1.100",
            remote_port=5004
        )
        
        session_id = session.session_id
        local_port = session.local_port
        
        # Cleanup session
        await rtp_manager.cleanup_session(session_id)
        
        # Session should be removed
        assert session_id not in rtp_manager.active_sessions
        assert local_port not in rtp_manager.port_allocations
    
    @pytest.mark.asyncio
    async def test_cleanup_all_sessions(self, rtp_manager):
        """Test cleanup of all sessions."""
        # Create multiple sessions
        sessions = []
        for i in range(3):
            session = await rtp_manager.create_session(
                local_port=10000 + i,
                remote_host=f"192.168.1.{100 + i}",
                remote_port=5004
            )
            sessions.append(session)
        
        assert len(rtp_manager.active_sessions) == 3
        
        # Cleanup all
        await rtp_manager.cleanup_all()
        
        assert len(rtp_manager.active_sessions) == 0
        assert len(rtp_manager.port_allocations) == 0
    
    @pytest.mark.asyncio
    async def test_session_statistics_tracking(self, rtp_manager, sample_rtp_packet):
        """Test session statistics tracking."""
        session = await rtp_manager.create_session(
            local_port=10000,
            remote_host="192.168.1.100",
            remote_port=5004
        )
        
        # Send packets to generate statistics
        for _ in range(10):
            await session.send_packet(sample_rtp_packet)
        
        stats = rtp_manager.get_session_statistics(session.session_id)
        assert stats is not None
        assert stats.packets_sent == 10
        assert stats.bytes_sent > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_session_handling(self, rtp_manager):
        """Test handling multiple concurrent sessions."""
        import asyncio
        
        # Create multiple sessions concurrently
        tasks = []
        for i in range(10):
            task = asyncio.create_task(rtp_manager.create_session(
                remote_host=f"192.168.1.{100 + i}",
                remote_port=5004 + i
            ))
            tasks.append(task)
        
        sessions = await asyncio.gather(*tasks)
        
        # All sessions should be created successfully
        assert len(sessions) == 10
        assert all(session is not None for session in sessions)
        assert len(rtp_manager.active_sessions) == 10
        
        # All ports should be unique
        ports = [session.local_port for session in sessions]
        assert len(set(ports)) == len(ports)


class TestAudioQuality:
    """Test audio quality validation and metrics."""
    
    def test_audio_quality_metrics(self, sample_audio_data, test_utils):
        """Test audio quality metrics calculation."""
        audio_data = sample_audio_data["pcm"]
        
        # Test audio quality assertion
        test_utils.assert_audio_quality(audio_data, 0.02, 8000)
        
        # Should not raise exception for valid audio
        assert len(audio_data) == 320  # 20ms at 8kHz, 16-bit = 160 samples * 2 bytes
    
    def test_audio_distortion_measurement(self, audio_processor):
        """Test audio distortion measurement."""
        # Create clean sine wave
        samples = 160
        t = np.linspace(0, 0.02, samples, False)
        clean_signal = np.sin(2 * np.pi * 1000 * t)
        clean_audio = (clean_signal * 32767).astype(np.int16).tobytes()
        
        # Add distortion
        distorted_signal = clean_signal + 0.1 * np.random.random(samples)
        distorted_audio = (distorted_signal * 32767).astype(np.int16).tobytes()
        
        # Measure THD (Total Harmonic Distortion)
        thd = audio_processor.calculate_thd(clean_audio, distorted_audio)
        
        assert 0 <= thd <= 1  # THD should be between 0 and 1
        assert thd < 0.2  # Should be reasonable distortion level
    
    def test_frequency_response_analysis(self, audio_processor):
        """Test frequency response analysis."""
        # Create multi-frequency test signal
        sample_rate = 8000
        duration = 0.1  # 100ms
        samples = int(sample_rate * duration)
        
        t = np.linspace(0, duration, samples, False)
        # Mix multiple frequencies
        signal = (np.sin(2 * np.pi * 300 * t) +  # 300 Hz
                 np.sin(2 * np.pi * 1000 * t) +  # 1000 Hz
                 np.sin(2 * np.pi * 2000 * t))   # 2000 Hz
        
        audio_data = (signal * 10000).astype(np.int16).tobytes()
        
        # Analyze frequency content
        frequencies, magnitudes = audio_processor.analyze_frequency_response(audio_data, sample_rate)
        
        assert len(frequencies) == len(magnitudes)
        assert max(frequencies) <= sample_rate / 2  # Nyquist limit
        
        # Should detect the three main frequencies
        peak_indices = np.where(magnitudes > np.max(magnitudes) * 0.5)[0]
        assert len(peak_indices) >= 3  # At least 3 significant peaks
    
    def test_signal_to_noise_ratio(self, audio_processor):
        """Test SNR calculation."""
        # Create signal with known SNR
        samples = 1600  # 200ms at 8kHz
        signal_power = 1000
        noise_power = 100
        
        signal = np.random.normal(0, np.sqrt(signal_power), samples)
        noise = np.random.normal(0, np.sqrt(noise_power), samples)
        combined = signal + noise
        
        audio_data = (combined * 1000).astype(np.int16).tobytes()
        
        # Calculate SNR
        snr_db = audio_processor.calculate_snr(audio_data)
        
        # Expected SNR = 10 * log10(signal_power / noise_power)
        expected_snr = 10 * np.log10(signal_power / noise_power)
        
        # Allow some tolerance due to random nature
        assert abs(snr_db - expected_snr) < 2.0  # Within 2 dB
    
    def test_audio_level_measurement(self, audio_processor, sample_audio_data):
        """Test audio level measurement."""
        audio_data = sample_audio_data["pcm"]
        
        # Measure RMS level
        rms_level = audio_processor.measure_rms_level(audio_data)
        assert rms_level >= 0
        
        # Measure peak level
        peak_level = audio_processor.measure_peak_level(audio_data)
        assert peak_level >= rms_level  # Peak should be >= RMS
        
        # Test with silence
        silent_audio = (np.zeros(160)).astype(np.int16).tobytes()
        silent_rms = audio_processor.measure_rms_level(silent_audio)
        assert silent_rms == 0.0
    
    def test_codec_quality_comparison(self, audio_processor, sample_audio_data):
        """Test codec quality comparison."""
        original_pcm = sample_audio_data["pcm"]
        
        # Convert through different codecs
        pcmu_converted = audio_processor.pcmu_to_pcm(
            audio_processor.pcm_to_pcmu(original_pcm)
        )
        pcma_converted = audio_processor.pcma_to_pcm(
            audio_processor.pcm_to_pcma(original_pcm)
        )
        
        # Calculate quality metrics
        pcmu_quality = audio_processor.calculate_codec_quality(original_pcm, pcmu_converted)
        pcma_quality = audio_processor.calculate_codec_quality(original_pcm, pcma_converted)
        
        # Both should have reasonable quality (> 0.7 correlation)
        assert pcmu_quality > 0.7
        assert pcma_quality > 0.7
        
        # Quality should be similar between codecs
        assert abs(pcmu_quality - pcma_quality) < 0.2
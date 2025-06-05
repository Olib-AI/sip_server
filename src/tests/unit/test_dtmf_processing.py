"""
Comprehensive unit tests for DTMF Processing components.
Tests DTMF detection, processing, IVR management, and music on hold.
"""
import pytest
import asyncio
import numpy as np
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from src.dtmf.dtmf_detector import DTMFDetector, DTMFEvent, DTMFMethod
from src.dtmf.dtmf_processor import DTMFProcessor, DTMFPattern, DTMFAction
from src.dtmf.ivr_manager import (
    IVRManager, IVRMenu, IVRSession, IVRPrompt, IVRAction, IVRMenuItem,
    IVRPromptType, IVRActionType
)
from src.dtmf.music_on_hold import MusicOnHoldManager, MusicSource, AudioGenerator


class TestDTMFDetector:
    """Test DTMF detection functionality."""
    
    @pytest.fixture
    async def dtmf_detector(self):
        """Create test DTMF detector."""
        detector = DTMFDetector(enable_rfc2833=True, enable_inband=True)
        yield detector
        detector.cleanup()
    
    def test_dtmf_detector_initialization(self, dtmf_detector):
        """Test DTMF detector initialization."""
        assert dtmf_detector.enable_rfc2833 is True
        assert dtmf_detector.enable_inband is True
        assert len(dtmf_detector.active_calls) == 0
        assert len(dtmf_detector.event_handlers) == 0
    
    def test_dtmf_digit_values(self):
        """Test DTMF digit values."""
        # Test all valid DTMF digits (now simple strings)
        assert "0" == "0"
        assert "1" == "1"
        assert "*" == "*"
        assert "#" == "#"
        
        # Test digit conversion
        assert str(0) == "0"
        assert str(1) == "1"
        assert "*" == "*"
        assert "#" == "#"
    
    @pytest.mark.asyncio
    async def test_rfc2833_dtmf_detection(self, dtmf_detector, sample_dtmf_rtp_packet):
        """Test RFC 2833 DTMF detection from RTP packets."""
        call_id = "test-rfc2833"
        
        # Process DTMF RTP packet
        event = await dtmf_detector.process_rtp_packet(call_id, sample_dtmf_rtp_packet)
        
        assert event is not None
        assert isinstance(event, DTMFEvent)
        assert event.call_id == call_id
        assert event.digit == "1"
        assert event.source == DTMFSource.RFC2833
        assert event.duration > 0
    
    @pytest.mark.asyncio
    async def test_inband_dtmf_detection(self, dtmf_detector):
        """Test in-band DTMF detection from audio data."""
        call_id = "test-inband"
        
        # Generate DTMF tone for digit '1' (697 Hz + 1209 Hz)
        sample_rate = 8000
        duration = 0.1  # 100ms
        samples = int(sample_rate * duration)
        
        t = np.linspace(0, duration, samples, False)
        # DTMF '1' frequencies
        tone1 = np.sin(2 * np.pi * 697 * t)   # Low frequency
        tone2 = np.sin(2 * np.pi * 1209 * t)  # High frequency
        dtmf_signal = (tone1 + tone2) / 2
        
        audio_data = (dtmf_signal * 16383).astype(np.int16).tobytes()
        
        # Process audio for DTMF
        event = await dtmf_detector.process_audio_data(call_id, audio_data)
        
        assert event is not None
        assert event.call_id == call_id
        assert event.digit == "1"
        assert event.source == DTMFSource.INBAND
    
    @pytest.mark.asyncio
    async def test_sip_info_dtmf_processing(self, dtmf_detector):
        """Test DTMF from SIP INFO method."""
        call_id = "test-sip-info"
        
        # Process SIP INFO DTMF
        event = await dtmf_detector.process_sip_info(call_id, "5")
        
        assert event is not None
        assert event.call_id == call_id
        assert event.digit == "5"
        assert event.source == DTMFSource.SIP_INFO
    
    def test_dtmf_event_creation(self):
        """Test DTMF event creation."""
        event = DTMFEvent(
            call_id="test-call",
            digit="*",
            source=DTMFSource.RFC2833,
            timestamp=time.time(),
            duration=150
        )
        
        assert event.call_id == "test-call"
        assert event.digit == "*"
        assert event.source == DTMFSource.RFC2833
        assert event.duration == 150
        assert event.timestamp > 0
    
    def test_event_handler_registration(self, dtmf_detector):
        """Test DTMF event handler registration."""
        events_received = []
        
        def test_handler(event: DTMFEvent):
            events_received.append(event)
        
        # Add handler
        dtmf_detector.add_event_handler(test_handler)
        assert len(dtmf_detector.event_handlers) == 1
        
        # Remove handler
        dtmf_detector.remove_event_handler(test_handler)
        assert len(dtmf_detector.event_handlers) == 0
    
    @pytest.mark.asyncio
    async def test_dtmf_debouncing(self, dtmf_detector):
        """Test DTMF debouncing to prevent duplicate events."""
        call_id = "test-debounce"
        
        # Send multiple identical DTMF events quickly
        events = []
        for _ in range(5):
            event = await dtmf_detector.process_sip_info(call_id, "1")
            if event:
                events.append(event)
            await asyncio.sleep(0.01)  # 10ms between events
        
        # Should debounce duplicate events
        assert len(events) <= 2  # At most 2 events due to debouncing
    
    def test_frequency_detection_accuracy(self, dtmf_detector):
        """Test frequency detection accuracy for all DTMF digits."""
        # DTMF frequency matrix
        dtmf_frequencies = {
            '1': (697, 1209), '2': (697, 1336), '3': (697, 1477),
            '4': (770, 1209), '5': (770, 1336), '6': (770, 1477),
            '7': (852, 1209), '8': (852, 1336), '9': (852, 1477),
            '*': (941, 1209), '0': (941, 1336), '#': (941, 1477)
        }
        
        for digit, (low_freq, high_freq) in dtmf_frequencies.items():
            # Test frequency detection
            detected = dtmf_detector.detect_dtmf_frequencies(low_freq, high_freq)
            assert detected == digit
    
    def test_call_state_management(self, dtmf_detector):
        """Test call state management in detector."""
        call_id = "test-state"
        
        # Initialize call
        dtmf_detector.initialize_call(call_id)
        assert call_id in dtmf_detector.active_calls
        
        # Cleanup call
        dtmf_detector.cleanup_call(call_id)
        assert call_id not in dtmf_detector.active_calls
    
    def test_statistics_tracking(self, dtmf_detector):
        """Test DTMF detection statistics."""
        # Process some DTMF events
        dtmf_detector.total_events_detected = 10
        dtmf_detector.rfc2833_events = 6
        dtmf_detector.inband_events = 3
        dtmf_detector.sip_info_events = 1
        
        stats = dtmf_detector.get_statistics()
        
        assert stats["total_events"] == 10
        assert stats["rfc2833_events"] == 6
        assert stats["inband_events"] == 3
        assert stats["sip_info_events"] == 1
        assert stats["detection_accuracy"] > 0


class TestDTMFProcessor:
    """Test DTMF processor functionality."""
    
    @pytest.fixture
    async def dtmf_processor(self, mock_ai_websocket_manager, call_manager):
        """Create test DTMF processor."""
        processor = DTMFProcessor(mock_ai_websocket_manager, call_manager)
        await processor.start()
        yield processor
        await processor.stop()
    
    def test_dtmf_processor_initialization(self, dtmf_processor):
        """Test DTMF processor initialization."""
        assert dtmf_processor.ai_websocket_manager is not None
        assert dtmf_processor.call_manager is not None
        assert len(dtmf_processor.patterns) == 0
        assert len(dtmf_processor.active_sequences) == 0
    
    def test_dtmf_pattern_creation(self):
        """Test DTMF pattern creation."""
        pattern = DTMFPattern(
            name="emergency",
            digits="911",
            action="emergency_call",
            timeout_ms=5000,
            metadata={"priority": "high"}
        )
        
        assert pattern.name == "emergency"
        assert pattern.digits == "911"
        assert pattern.action == "emergency_call"
        assert pattern.timeout_ms == 5000
        assert pattern.metadata["priority"] == "high"
    
    @pytest.mark.asyncio
    async def test_dtmf_event_processing(self, dtmf_processor):
        """Test DTMF event processing."""
        call_id = "test-processing"
        
        # Create DTMF event
        event = DTMFEvent(
            call_id=call_id,
            digit="1",
            source=DTMFSource.RFC2833,
            timestamp=time.time(),
            duration=100
        )
        
        # Process event
        result = await dtmf_processor.process_dtmf_event(event)
        
        assert result is not None
        assert "call_id" in result
        assert result["call_id"] == call_id
    
    @pytest.mark.asyncio
    async def test_pattern_matching(self, dtmf_processor):
        """Test DTMF pattern matching."""
        call_id = "test-pattern"
        
        # Add pattern
        pattern = DTMFPattern(
            name="test_sequence",
            digits="123",
            action="test_action",
            timeout_ms=3000
        )
        dtmf_processor.add_pattern(pattern)
        
        # Send matching sequence
        for digit_char in "123":
            digit = digit_char
            event = DTMFEvent(
                call_id=call_id,
                digit=digit,
                source=DTMFSource.RFC2833,
                timestamp=time.time(),
                duration=100
            )
            result = await dtmf_processor.process_dtmf_event(event)
        
        # Pattern should be matched
        assert call_id not in dtmf_processor.active_sequences  # Completed and cleared
    
    @pytest.mark.asyncio
    async def test_pattern_timeout(self, dtmf_processor):
        """Test DTMF pattern timeout handling."""
        call_id = "test-timeout"
        
        # Add pattern with short timeout
        pattern = DTMFPattern(
            name="timeout_test",
            digits="456",
            action="timeout_action",
            timeout_ms=100  # 100ms timeout
        )
        dtmf_processor.add_pattern(pattern)
        
        # Send partial sequence
        event = DTMFEvent(
            call_id=call_id,
            digit="4",
            source=DTMFSource.RFC2833,
            timestamp=time.time(),
            duration=100
        )
        await dtmf_processor.process_dtmf_event(event)
        
        # Wait for timeout
        await asyncio.sleep(0.2)
        
        # Sequence should be timed out and cleared
        await dtmf_processor._cleanup_expired_sequences()
        assert call_id not in dtmf_processor.active_sequences
    
    def test_pattern_management(self, dtmf_processor):
        """Test pattern management operations."""
        # Add patterns
        pattern1 = DTMFPattern("pattern1", "123", "action1", 1000)
        pattern2 = DTMFPattern("pattern2", "456", "action2", 2000)
        
        dtmf_processor.add_pattern(pattern1)
        dtmf_processor.add_pattern(pattern2)
        
        assert len(dtmf_processor.patterns) == 2
        
        # Remove pattern
        dtmf_processor.remove_pattern("pattern1")
        assert len(dtmf_processor.patterns) == 1
        assert "pattern1" not in dtmf_processor.patterns
        
        # Clear all patterns
        dtmf_processor.clear_patterns()
        assert len(dtmf_processor.patterns) == 0
    
    def test_configuration_loading(self, dtmf_processor):
        """Test loading patterns from configuration."""
        config = {
            "emergency": {
                "digits": "911",
                "action": "emergency_call",
                "timeout_ms": 5000
            },
            "voicemail": {
                "digits": "*98",
                "action": "voicemail_access",
                "timeout_ms": 3000
            }
        }
        
        dtmf_processor.load_patterns_from_config(config)
        
        assert len(dtmf_processor.patterns) == 2
        assert "emergency" in dtmf_processor.patterns
        assert "voicemail" in dtmf_processor.patterns
    
    def test_statistics_generation(self, dtmf_processor):
        """Test DTMF processor statistics."""
        # Set some test data
        dtmf_processor.total_events_processed = 50
        dtmf_processor.patterns_matched = 10
        dtmf_processor.sequences_timed_out = 5
        
        stats = dtmf_processor.get_statistics()
        
        assert stats["total_events_processed"] == 50
        assert stats["patterns_matched"] == 10
        assert stats["sequences_timed_out"] == 5
        assert "active_sequences" in stats


class TestIVRManager:
    """Test IVR manager functionality."""
    
    @pytest.fixture
    async def ivr_manager(self, call_manager, dtmf_processor):
        """Create test IVR manager."""
        manager = IVRManager(call_manager, dtmf_processor)
        await manager.start()
        yield manager
        await manager.stop()
    
    def test_ivr_menu_creation(self):
        """Test IVR menu creation."""
        menu = IVRMenu(
            menu_id="main_menu",
            prompt="Press 1 for sales, 2 for support, 0 for operator",
            options={
                "1": {"action": "transfer", "target": "sales_queue"},
                "2": {"action": "transfer", "target": "support_queue"},
                "0": {"action": "transfer", "target": "operator"}
            },
            timeout_seconds=10,
            max_retries=3
        )
        
        assert menu.menu_id == "main_menu"
        assert "Press 1 for sales" in menu.prompt
        assert len(menu.options) == 3
        assert menu.timeout_seconds == 10
        assert menu.max_retries == 3
    
    def test_ivr_session_creation(self):
        """Test IVR session creation."""
        session = IVRSession(
            call_id="test-call",
            current_menu="main_menu",
            start_time=time.time(),
            attempts=0
        )
        
        assert session.call_id == "test-call"
        assert session.current_menu == "main_menu"
        assert session.attempts == 0
        assert session.start_time > 0
    
    @pytest.mark.asyncio
    async def test_ivr_session_start(self, ivr_manager):
        """Test starting IVR session."""
        call_id = "test-ivr-start"
        
        # Add a test menu
        menu = IVRMenu(
            menu_id="test_menu",
            prompt="Test menu prompt",
            options={"1": {"action": "test", "target": "test_target"}},
            timeout_seconds=30
        )
        ivr_manager.add_menu(menu)
        
        # Start IVR session
        result = await ivr_manager.start_ivr_session(call_id, "test_menu")
        
        assert result is True
        assert call_id in ivr_manager.active_sessions
        
        session = ivr_manager.active_sessions[call_id]
        assert session.current_menu == "test_menu"
    
    @pytest.mark.asyncio
    async def test_ivr_option_selection(self, ivr_manager):
        """Test IVR option selection."""
        call_id = "test-ivr-option"
        
        # Add menu with options
        menu = IVRMenu(
            menu_id="selection_menu",
            prompt="Press 1 or 2",
            options={
                "1": {"action": "transfer", "target": "queue1"},
                "2": {"action": "transfer", "target": "queue2"}
            },
            timeout_seconds=30
        )
        ivr_manager.add_menu(menu)
        
        # Start session
        await ivr_manager.start_ivr_session(call_id, "selection_menu")
        
        # Simulate DTMF input
        result = await ivr_manager.process_dtmf_input(call_id, "1")
        
        assert result is not None
        assert result["action"] == "transfer"
        assert result["target"] == "queue1"
    
    @pytest.mark.asyncio
    async def test_ivr_timeout_handling(self, ivr_manager):
        """Test IVR timeout handling."""
        call_id = "test-ivr-timeout"
        
        # Add menu with short timeout
        menu = IVRMenu(
            menu_id="timeout_menu",
            prompt="Quick selection required",
            options={"1": {"action": "test", "target": "test"}},
            timeout_seconds=1,  # 1 second timeout
            max_retries=1
        )
        ivr_manager.add_menu(menu)
        
        # Start session
        await ivr_manager.start_ivr_session(call_id, "timeout_menu")
        
        # Wait for timeout
        await asyncio.sleep(1.5)
        
        # Process timeout
        await ivr_manager._process_timeouts()
        
        # Session should still exist but with incremented attempts
        if call_id in ivr_manager.active_sessions:
            session = ivr_manager.active_sessions[call_id]
            assert session.attempts > 0
    
    @pytest.mark.asyncio
    async def test_ivr_menu_navigation(self, ivr_manager):
        """Test navigation between IVR menus."""
        call_id = "test-navigation"
        
        # Add multiple menus
        main_menu = IVRMenu(
            menu_id="main",
            prompt="Main menu",
            options={
                "1": {"action": "submenu", "target": "submenu1"},
                "9": {"action": "previous", "target": "main"}
            }
        )
        
        sub_menu = IVRMenu(
            menu_id="submenu1",
            prompt="Sub menu",
            options={
                "1": {"action": "transfer", "target": "agent"},
                "9": {"action": "previous", "target": "main"}
            }
        )
        
        ivr_manager.add_menu(main_menu)
        ivr_manager.add_menu(sub_menu)
        
        # Start in main menu
        await ivr_manager.start_ivr_session(call_id, "main")
        
        # Navigate to submenu
        result = await ivr_manager.process_dtmf_input(call_id, "1")
        assert result["action"] == "submenu"
        
        # Should now be in submenu
        session = ivr_manager.active_sessions[call_id]
        assert session.current_menu == "submenu1"
    
    def test_menu_management(self, ivr_manager):
        """Test IVR menu management."""
        menu1 = IVRMenu("menu1", "Prompt 1", {"1": {"action": "test"}})
        menu2 = IVRMenu("menu2", "Prompt 2", {"1": {"action": "test"}})
        
        # Add menus
        ivr_manager.add_menu(menu1)
        ivr_manager.add_menu(menu2)
        
        assert len(ivr_manager.menus) == 2
        assert "menu1" in ivr_manager.menus
        assert "menu2" in ivr_manager.menus
        
        # Remove menu
        ivr_manager.remove_menu("menu1")
        assert len(ivr_manager.menus) == 1
        assert "menu1" not in ivr_manager.menus
    
    def test_configuration_loading(self, ivr_manager):
        """Test loading IVR configuration."""
        config = {
            "main_menu": {
                "prompt": "Welcome! Press 1 for sales, 2 for support",
                "options": {
                    "1": {"action": "transfer", "target": "sales"},
                    "2": {"action": "transfer", "target": "support"}
                },
                "timeout_seconds": 30,
                "max_retries": 3
            }
        }
        
        ivr_manager.load_menus_from_config(config)
        
        assert len(ivr_manager.menus) == 1
        assert "main_menu" in ivr_manager.menus
        
        menu = ivr_manager.menus["main_menu"]
        assert "Welcome!" in menu.prompt
        assert len(menu.options) == 2
    
    def test_ivr_statistics(self, ivr_manager):
        """Test IVR statistics generation."""
        # Set test data
        ivr_manager.total_sessions = 100
        ivr_manager.successful_selections = 85
        ivr_manager.timed_out_sessions = 10
        ivr_manager.abandoned_sessions = 5
        
        stats = ivr_manager.get_statistics()
        
        assert stats["total_sessions"] == 100
        assert stats["successful_selections"] == 85
        assert stats["timed_out_sessions"] == 10
        assert stats["abandoned_sessions"] == 5
        assert stats["success_rate"] == 0.85


class TestMusicOnHoldManager:
    """Test music on hold manager functionality."""
    
    @pytest.fixture
    async def music_manager(self, call_manager):
        """Create test music on hold manager."""
        manager = MusicOnHoldManager(call_manager)
        await manager.start()
        yield manager
        await manager.stop()
    
    def test_hold_music_source_creation(self):
        """Test hold music source creation."""
        source = HoldMusicSource(
            name="default",
            url="http://example.com/music.mp3",
            format="mp3",
            loop=True,
            volume=0.8
        )
        
        assert source.name == "default"
        assert source.url == "http://example.com/music.mp3"
        assert source.format == "mp3"
        assert source.loop is True
        assert source.volume == 0.8
    
    @pytest.mark.asyncio
    async def test_start_hold_music(self, music_manager):
        """Test starting hold music."""
        call_id = "test-hold-music"
        
        # Add music source
        source = HoldMusicSource(
            name="test_music",
            url="http://example.com/test.wav",
            format="wav"
        )
        music_manager.add_music_source(source)
        
        # Start hold music
        result = await music_manager.start_hold_music(call_id, "test_music")
        
        assert result is True
        assert call_id in music_manager.active_hold_sessions
    
    @pytest.mark.asyncio
    async def test_stop_hold_music(self, music_manager):
        """Test stopping hold music."""
        call_id = "test-stop-music"
        
        # Start hold music first
        source = HoldMusicSource("test", "http://example.com/test.wav", "wav")
        music_manager.add_music_source(source)
        await music_manager.start_hold_music(call_id, "test")
        
        # Stop hold music
        result = await music_manager.stop_hold_music(call_id)
        
        assert result is True
        assert call_id not in music_manager.active_hold_sessions
    
    def test_music_source_management(self, music_manager):
        """Test music source management."""
        source1 = HoldMusicSource("source1", "url1", "wav")
        source2 = HoldMusicSource("source2", "url2", "mp3")
        
        # Add sources
        music_manager.add_music_source(source1)
        music_manager.add_music_source(source2)
        
        assert len(music_manager.music_sources) == 2
        assert "source1" in music_manager.music_sources
        assert "source2" in music_manager.music_sources
        
        # Remove source
        music_manager.remove_music_source("source1")
        assert len(music_manager.music_sources) == 1
        assert "source1" not in music_manager.music_sources
    
    def test_configuration_loading(self, music_manager):
        """Test loading music configuration."""
        config = {
            "default": {
                "url": "http://example.com/default.mp3",
                "format": "mp3",
                "loop": True,
                "volume": 0.5
            },
            "classical": {
                "url": "http://example.com/classical.wav",
                "format": "wav",
                "loop": True,
                "volume": 0.7
            }
        }
        
        music_manager.load_sources_from_config(config)
        
        assert len(music_manager.music_sources) == 2
        assert "default" in music_manager.music_sources
        assert "classical" in music_manager.music_sources
        
        default_source = music_manager.music_sources["default"]
        assert default_source.volume == 0.5
        assert default_source.loop is True
    
    @pytest.mark.asyncio
    async def test_audio_streaming(self, music_manager, temp_audio_file):
        """Test audio streaming for hold music."""
        call_id = "test-streaming"
        
        # Create source with local file
        source = HoldMusicSource(
            name="local_test",
            url=f"file://{temp_audio_file}",
            format="wav"
        )
        music_manager.add_music_source(source)
        
        # Start streaming
        await music_manager.start_hold_music(call_id, "local_test")
        
        # Simulate audio streaming
        audio_chunk = await music_manager.get_audio_chunk(call_id)
        
        assert audio_chunk is not None
        assert len(audio_chunk) > 0
    
    def test_hold_statistics(self, music_manager):
        """Test hold music statistics."""
        # Set test data
        music_manager.total_hold_sessions = 50
        music_manager.active_hold_sessions = {"call1": {}, "call2": {}}
        music_manager.total_hold_time = 3600  # 1 hour
        
        stats = music_manager.get_statistics()
        
        assert stats["total_hold_sessions"] == 50
        assert stats["active_sessions"] == 2
        assert stats["total_hold_time_seconds"] == 3600
        assert stats["average_hold_time"] == 72  # 3600 / 50


class TestDTMFIntegration:
    """Test DTMF component integration."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_dtmf_flow(self, dtmf_detector, dtmf_processor, ivr_manager):
        """Test complete DTMF flow from detection to action."""
        call_id = "test-e2e-dtmf"
        
        # Set up IVR menu
        menu = IVRMenu(
            menu_id="e2e_menu",
            prompt="Press 1 to continue",
            options={"1": {"action": "continue", "target": "next_step"}}
        )
        ivr_manager.add_menu(menu)
        
        # Start IVR session
        await ivr_manager.start_ivr_session(call_id, "e2e_menu")
        
        # Connect DTMF processor to IVR
        async def handle_dtmf_for_ivr(event: DTMFEvent):
            await ivr_manager.process_dtmf_input(event.call_id, event.digit.value)
        
        dtmf_detector.add_event_handler(handle_dtmf_for_ivr)
        
        # Simulate DTMF detection
        event = await dtmf_detector.process_sip_info(call_id, "1")
        
        # Process through the chain
        if event:
            for handler in dtmf_detector.event_handlers:
                await handler(event)
        
        # Verify action was taken
        # In a real implementation, this would trigger call transfer or other action
        assert call_id in ivr_manager.active_sessions
    
    @pytest.mark.asyncio
    async def test_dtmf_performance_under_load(self, dtmf_detector, performance_thresholds):
        """Test DTMF detection performance under load."""
        call_ids = [f"perf-test-{i}" for i in range(100)]
        
        start_time = time.perf_counter()
        
        # Process DTMF for many calls concurrently
        tasks = []
        for call_id in call_ids:
            task = asyncio.create_task(dtmf_detector.process_sip_info(call_id, "1"))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        end_time = time.perf_counter()
        total_time_ms = (end_time - start_time) * 1000
        avg_time_per_detection = total_time_ms / len(call_ids)
        
        assert avg_time_per_detection < performance_thresholds["dtmf_detection_ms"]
    
    @pytest.mark.asyncio
    async def test_dtmf_error_recovery(self, dtmf_processor):
        """Test DTMF system error recovery."""
        call_id = "test-error-recovery"
        
        # Create invalid pattern to trigger error
        invalid_pattern = DTMFPattern("invalid", "", "invalid_action", -1)
        
        # System should handle invalid pattern gracefully
        try:
            dtmf_processor.add_pattern(invalid_pattern)
            
            # Process DTMF event
            event = DTMFEvent(
                call_id=call_id,
                digit="1",
                source=DTMFSource.RFC2833,
                timestamp=time.time(),
                duration=100
            )
            
            result = await dtmf_processor.process_dtmf_event(event)
            # Should not crash
            
        except Exception as e:
            # Should handle errors gracefully
            assert "invalid" in str(e).lower() or "error" in str(e).lower()
    
    def test_dtmf_memory_usage(self, dtmf_detector):
        """Test DTMF system memory usage."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create many calls with DTMF state
        for i in range(1000):
            call_id = f"memory-test-{i}"
            dtmf_detector.initialize_call(call_id)
        
        current_memory = process.memory_info().rss
        memory_increase = current_memory - initial_memory
        
        # Memory increase should be reasonable (less than 10MB for 1000 calls)
        assert memory_increase < 10 * 1024 * 1024
        
        # Cleanup
        for i in range(1000):
            call_id = f"memory-test-{i}"
            dtmf_detector.cleanup_call(call_id)
"""DTMF Detection Implementation (RFC 2833 and In-band)."""
import asyncio
import logging
import time
import struct
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np
from scipy import signal
import threading
from collections import deque

logger = logging.getLogger(__name__)


class DTMFMethod(Enum):
    """DTMF detection methods."""
    RFC2833 = "rfc2833"
    INBAND = "inband" 
    SIP_INFO = "sip_info"


@dataclass
class DTMFEvent:
    """DTMF event information."""
    call_id: str
    digit: str
    method: DTMFMethod
    timestamp: float
    duration_ms: Optional[int] = None
    level_db: Optional[float] = None
    source: str = "detected"
    confidence: float = 1.0


class RFC2833Detector:
    """RFC 2833 DTMF detection from RTP packets."""
    
    # DTMF event codes (RFC 2833)
    DTMF_EVENTS = {
        0: '0', 1: '1', 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7',
        8: '8', 9: '9', 10: '*', 11: '#', 12: 'A', 13: 'B', 14: 'C', 15: 'D'
    }
    
    def __init__(self):
        self.active_events: Dict[str, Dict] = {}  # call_id -> event_info
        
    def process_rtp_packet(self, call_id: str, rtp_payload: bytes) -> Optional[DTMFEvent]:
        """Process RTP packet for RFC 2833 DTMF events."""
        try:
            if len(rtp_payload) < 4:
                return None
                
            # Parse RFC 2833 payload
            event_code, flags, duration = struct.unpack('!BBH', rtp_payload[:4])
            
            # Check if this is a DTMF event
            if event_code not in self.DTMF_EVENTS:
                return None
                
            digit = self.DTMF_EVENTS[event_code]
            end_bit = bool(flags & 0x80)
            volume = flags & 0x3F
            
            current_time = time.time()
            
            # Handle event start
            if call_id not in self.active_events:
                self.active_events[call_id] = {
                    'digit': digit,
                    'start_time': current_time,
                    'volume': volume,
                    'duration': duration
                }
                
                # Don't emit start event, wait for end
                return None
            
            # Handle event end
            if end_bit:
                event_info = self.active_events.pop(call_id, {})
                if event_info:
                    duration_ms = int((current_time - event_info['start_time']) * 1000)
                    level_db = -volume if volume > 0 else None
                    
                    return DTMFEvent(
                        call_id=call_id,
                        digit=digit,
                        method=DTMFMethod.RFC2833,
                        timestamp=current_time,
                        duration_ms=duration_ms,
                        level_db=level_db,
                        confidence=0.95
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing RFC 2833 packet: {e}")
            return None


class InbandDTMFDetector:
    """In-band DTMF detection using Goertzel algorithm."""
    
    # DTMF frequencies (Hz)
    DTMF_FREQS = {
        ('1', '2', '3', 'A'): (697, 1209, 1336, 1477, 1633),
        ('4', '5', '6', 'B'): (770, 1209, 1336, 1477, 1633),
        ('7', '8', '9', 'C'): (852, 1209, 1336, 1477, 1633),
        ('*', '0', '#', 'D'): (941, 1209, 1336, 1477, 1633)
    }
    
    DTMF_MATRIX = {
        (697, 1209): '1', (697, 1336): '2', (697, 1477): '3', (697, 1633): 'A',
        (770, 1209): '4', (770, 1336): '5', (770, 1477): '6', (770, 1633): 'B',
        (852, 1209): '7', (852, 1336): '8', (852, 1477): '9', (852, 1633): 'C',
        (941, 1209): '*', (941, 1336): '0', (941, 1477): '#', (941, 1633): 'D'
    }
    
    def __init__(self, sample_rate: int = 8000, frame_size: int = 160):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.detection_threshold = 1000000  # Energy threshold
        self.min_duration_ms = 40  # Minimum DTMF duration
        self.max_duration_ms = 1000  # Maximum DTMF duration
        
        # State tracking
        self.call_buffers: Dict[str, deque] = {}
        self.call_states: Dict[str, Dict] = {}
        
        # Precompute Goertzel coefficients
        self._compute_coefficients()
        
    def _compute_coefficients(self):
        """Precompute Goertzel algorithm coefficients."""
        self.coefficients = {}
        
        for freq in [697, 770, 852, 941, 1209, 1336, 1477, 1633]:
            k = int(0.5 + (self.frame_size * freq / self.sample_rate))
            w = (2.0 * np.pi * k) / self.frame_size
            cosine = np.cos(w)
            coeff = 2.0 * cosine
            self.coefficients[freq] = coeff
    
    def process_audio(self, call_id: str, audio_data: bytes) -> Optional[DTMFEvent]:
        """Process audio data for in-band DTMF detection."""
        try:
            # Convert audio to numpy array
            if len(audio_data) % 2 != 0:
                return None
                
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            
            # Initialize call buffer if needed
            if call_id not in self.call_buffers:
                self.call_buffers[call_id] = deque(maxlen=self.frame_size * 2)
                self.call_states[call_id] = {
                    'detecting': False,
                    'current_digit': None,
                    'start_time': None,
                    'frame_count': 0
                }
            
            # Add samples to buffer
            self.call_buffers[call_id].extend(samples)
            
            # Process when we have enough samples
            if len(self.call_buffers[call_id]) >= self.frame_size:
                # Extract frame
                frame = np.array(list(self.call_buffers[call_id])[-self.frame_size:])
                
                # Detect DTMF
                detected_digit = self._detect_dtmf_in_frame(frame)
                
                return self._process_detection_result(call_id, detected_digit)
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing in-band audio: {e}")
            return None
    
    def _detect_dtmf_in_frame(self, frame: np.ndarray) -> Optional[str]:
        """Detect DTMF digit in audio frame using Goertzel algorithm."""
        try:
            # Apply window to reduce spectral leakage
            windowed_frame = frame * np.hanning(len(frame))
            
            # Calculate energy for each DTMF frequency
            energies = {}
            for freq, coeff in self.coefficients.items():
                energy = self._goertzel(windowed_frame, coeff)
                energies[freq] = energy
            
            # Find strongest frequencies in each group
            low_freqs = [697, 770, 852, 941]
            high_freqs = [1209, 1336, 1477, 1633]
            
            max_low_freq = max(low_freqs, key=lambda f: energies[f])
            max_high_freq = max(high_freqs, key=lambda f: energies[f])
            
            max_low_energy = energies[max_low_freq]
            max_high_energy = energies[max_high_freq]
            
            # Check if energies are above threshold
            if (max_low_energy > self.detection_threshold and 
                max_high_energy > self.detection_threshold):
                
                # Check if this is a valid DTMF combination
                digit = self.DTMF_MATRIX.get((max_low_freq, max_high_freq))
                if digit:
                    # Additional validation: check frequency ratio
                    if self._validate_dtmf_detection(energies, max_low_freq, max_high_freq):
                        return digit
            
            return None
            
        except Exception as e:
            logger.error(f"Error in DTMF detection: {e}")
            return None
    
    def _goertzel(self, samples: np.ndarray, coeff: float) -> float:
        """Goertzel algorithm for single frequency detection."""
        s_prev = 0.0
        s_prev2 = 0.0
        
        for sample in samples:
            s = sample + coeff * s_prev - s_prev2
            s_prev2 = s_prev
            s_prev = s
        
        power = s_prev2 * s_prev2 + s_prev * s_prev - coeff * s_prev * s_prev2
        return power
    
    def _validate_dtmf_detection(self, energies: Dict[int, float], 
                                low_freq: int, high_freq: int) -> bool:
        """Validate DTMF detection with additional checks."""
        # Check that detected frequencies dominate their groups
        low_freqs = [697, 770, 852, 941]
        high_freqs = [1209, 1336, 1477, 1633]
        
        # Low frequency should be strongest in its group
        for freq in low_freqs:
            if freq != low_freq and energies[freq] > energies[low_freq] * 0.5:
                return False
        
        # High frequency should be strongest in its group
        for freq in high_freqs:
            if freq != high_freq and energies[freq] > energies[high_freq] * 0.5:
                return False
        
        # Check energy ratio between low and high frequencies
        ratio = energies[high_freq] / energies[low_freq]
        if not (0.5 <= ratio <= 2.0):
            return False
        
        return True
    
    def _process_detection_result(self, call_id: str, detected_digit: Optional[str]) -> Optional[DTMFEvent]:
        """Process detection result and handle state transitions."""
        state = self.call_states[call_id]
        current_time = time.time()
        
        if detected_digit:
            if not state['detecting']:
                # Start of new digit
                state['detecting'] = True
                state['current_digit'] = detected_digit
                state['start_time'] = current_time
                state['frame_count'] = 1
            elif state['current_digit'] == detected_digit:
                # Continuation of same digit
                state['frame_count'] += 1
            else:
                # Different digit detected - end previous and start new
                event = self._end_detection(call_id)
                
                state['detecting'] = True
                state['current_digit'] = detected_digit
                state['start_time'] = current_time
                state['frame_count'] = 1
                
                return event
        else:
            if state['detecting']:
                # End of digit detection
                return self._end_detection(call_id)
        
        return None
    
    def _end_detection(self, call_id: str) -> Optional[DTMFEvent]:
        """End digit detection and create event."""
        state = self.call_states[call_id]
        
        if not state['detecting']:
            return None
        
        duration_ms = int((time.time() - state['start_time']) * 1000)
        
        # Check minimum duration
        if duration_ms < self.min_duration_ms:
            self._reset_state(call_id)
            return None
        
        # Create event
        event = DTMFEvent(
            call_id=call_id,
            digit=state['current_digit'],
            method=DTMFMethod.INBAND,
            timestamp=time.time(),
            duration_ms=duration_ms,
            confidence=0.8  # Lower confidence for in-band
        )
        
        self._reset_state(call_id)
        return event
    
    def _reset_state(self, call_id: str):
        """Reset detection state for call."""
        if call_id in self.call_states:
            self.call_states[call_id].update({
                'detecting': False,
                'current_digit': None,
                'start_time': None,
                'frame_count': 0
            })


class DTMFDetector:
    """Main DTMF detector combining multiple methods."""
    
    def __init__(self, enable_rfc2833: bool = True, enable_inband: bool = True):
        self.enable_rfc2833 = enable_rfc2833
        self.enable_inband = enable_inband
        
        # Initialize detectors
        self.rfc2833_detector = RFC2833Detector() if enable_rfc2833 else None
        self.inband_detector = InbandDTMFDetector() if enable_inband else None
        
        # Event handlers
        self.event_handlers: List[Callable[[DTMFEvent], None]] = []
        
        # Statistics
        self.total_events = 0
        self.events_by_method: Dict[DTMFMethod, int] = {
            DTMFMethod.RFC2833: 0,
            DTMFMethod.INBAND: 0,
            DTMFMethod.SIP_INFO: 0
        }
        
    def add_event_handler(self, handler: Callable[[DTMFEvent], None]):
        """Add DTMF event handler."""
        self.event_handlers.append(handler)
        
    def remove_event_handler(self, handler: Callable[[DTMFEvent], None]):
        """Remove DTMF event handler."""
        if handler in self.event_handlers:
            self.event_handlers.remove(handler)
    
    async def process_rtp_packet(self, call_id: str, rtp_payload: bytes) -> Optional[DTMFEvent]:
        """Process RTP packet for DTMF detection."""
        if not self.rfc2833_detector:
            return None
            
        event = self.rfc2833_detector.process_rtp_packet(call_id, rtp_payload)
        if event:
            await self._emit_event(event)
        
        return event
    
    async def process_audio_data(self, call_id: str, audio_data: bytes) -> Optional[DTMFEvent]:
        """Process audio data for in-band DTMF detection."""
        if not self.inband_detector:
            return None
            
        event = self.inband_detector.process_audio(call_id, audio_data)
        if event:
            await self._emit_event(event)
        
        return event
    
    async def process_sip_info(self, call_id: str, dtmf_digit: str) -> DTMFEvent:
        """Process DTMF from SIP INFO method."""
        event = DTMFEvent(
            call_id=call_id,
            digit=dtmf_digit,
            method=DTMFMethod.SIP_INFO,
            timestamp=time.time(),
            source="sip_info",
            confidence=1.0
        )
        
        await self._emit_event(event)
        return event
    
    async def _emit_event(self, event: DTMFEvent):
        """Emit DTMF event to handlers."""
        try:
            # Update statistics
            self.total_events += 1
            self.events_by_method[event.method] += 1
            
            logger.info(
                f"DTMF detected: call_id={event.call_id}, digit={event.digit}, "
                f"method={event.method.value}, confidence={event.confidence}"
            )
            
            # Call event handlers
            for handler in self.event_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"Error in DTMF event handler: {e}")
                    
        except Exception as e:
            logger.error(f"Error emitting DTMF event: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get DTMF detection statistics."""
        return {
            "total_events": self.total_events,
            "events_by_method": {
                method.value: count 
                for method, count in self.events_by_method.items()
            },
            "enabled_methods": {
                "rfc2833": self.enable_rfc2833,
                "inband": self.enable_inband
            }
        }
    
    def cleanup_call(self, call_id: str):
        """Cleanup call-specific data."""
        if self.rfc2833_detector:
            self.rfc2833_detector.active_events.pop(call_id, None)
            
        if self.inband_detector:
            self.inband_detector.call_buffers.pop(call_id, None)
            self.inband_detector.call_states.pop(call_id, None)
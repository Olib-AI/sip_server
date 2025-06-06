"""Music on Hold Implementation."""
import asyncio
import logging
import os
import wave
import struct
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import threading
from pathlib import Path
import random

logger = logging.getLogger(__name__)


class MusicSourceType(Enum):
    """Music source types."""
    FILE = "file"
    STREAM = "stream"
    GENERATED = "generated"


@dataclass
class MusicSource:
    """Music source configuration."""
    name: str
    source_type: MusicSourceType
    path: Optional[str] = None
    url: Optional[str] = None
    loop: bool = True
    volume: float = 0.8
    sample_rate: int = 8000
    channels: int = 1
    bits_per_sample: int = 16
    
    def __post_init__(self):
        """Validate source configuration."""
        if self.source_type == MusicSourceType.FILE and not self.path:
            raise ValueError("File source requires path")
        elif self.source_type == MusicSourceType.STREAM and not self.url:
            raise ValueError("Stream source requires URL")


class AudioGenerator:
    """Generate audio tones and patterns."""
    
    @staticmethod
    def generate_tone(frequency: float, duration: float, sample_rate: int = 8000, 
                     amplitude: float = 0.3) -> bytes:
        """Generate a sine wave tone."""
        import math
        
        num_samples = int(duration * sample_rate)
        samples = []
        
        for i in range(num_samples):
            t = i / sample_rate
            sample = amplitude * math.sin(2 * math.pi * frequency * t)
            # Convert to 16-bit PCM
            sample_int = int(sample * 32767)
            samples.append(struct.pack('<h', sample_int))
        
        return b''.join(samples)
    
    @staticmethod
    def generate_silence(duration: float, sample_rate: int = 8000) -> bytes:
        """Generate silence."""
        num_samples = int(duration * sample_rate)
        return b'\x00\x00' * num_samples
    
    @staticmethod
    def generate_ring_tone(duration: float = 1.0, sample_rate: int = 8000) -> bytes:
        """Generate a ring tone pattern."""
        # Ring tone: 440Hz + 480Hz for 2 seconds, silence for 4 seconds
        ring_duration = 2.0
        silence_duration = 4.0
        
        audio_data = b''
        current_time = 0.0
        
        while current_time < duration:
            # Ring portion
            if current_time + ring_duration <= duration:
                # Mix 440Hz and 480Hz
                tone1 = AudioGenerator.generate_tone(440, ring_duration, sample_rate, 0.2)
                tone2 = AudioGenerator.generate_tone(480, ring_duration, sample_rate, 0.2)
                
                # Mix the tones
                mixed = AudioGenerator._mix_audio([tone1, tone2])
                audio_data += mixed
                current_time += ring_duration
            else:
                # Partial ring
                remaining = duration - current_time
                tone1 = AudioGenerator.generate_tone(440, remaining, sample_rate, 0.2)
                tone2 = AudioGenerator.generate_tone(480, remaining, sample_rate, 0.2)
                mixed = AudioGenerator._mix_audio([tone1, tone2])
                audio_data += mixed
                break
            
            # Silence portion
            if current_time + silence_duration <= duration:
                silence = AudioGenerator.generate_silence(silence_duration, sample_rate)
                audio_data += silence
                current_time += silence_duration
            else:
                # Partial silence
                remaining = duration - current_time
                if remaining > 0:
                    silence = AudioGenerator.generate_silence(remaining, sample_rate)
                    audio_data += silence
                break
        
        return audio_data
    
    @staticmethod
    def _mix_audio(audio_streams: List[bytes]) -> bytes:
        """Mix multiple audio streams."""
        if not audio_streams:
            return b''
        
        # Ensure all streams are the same length
        min_length = min(len(stream) for stream in audio_streams)
        
        mixed_samples = []
        for i in range(0, min_length, 2):  # 2 bytes per sample (16-bit)
            sample_sum = 0
            
            for stream in audio_streams:
                if i + 1 < len(stream):
                    sample = struct.unpack('<h', stream[i:i+2])[0]
                    sample_sum += sample
            
            # Average and clamp
            mixed_sample = sample_sum // len(audio_streams)
            mixed_sample = max(-32768, min(32767, mixed_sample))
            
            mixed_samples.append(struct.pack('<h', mixed_sample))
        
        return b''.join(mixed_samples)


class MusicPlayer:
    """Audio player for music on hold."""
    
    def __init__(self, source: MusicSource):
        self.source = source
        self.audio_data: Optional[bytes] = None
        self.position = 0
        self.is_playing = False
        self.loop_count = 0
        
        # Load audio data
        asyncio.create_task(self._load_audio())
    
    async def _load_audio(self):
        """Load audio data based on source type."""
        try:
            if self.source.source_type == MusicSourceType.FILE:
                await self._load_from_file()
            elif self.source.source_type == MusicSourceType.STREAM:
                await self._load_from_stream()
            elif self.source.source_type == MusicSourceType.GENERATED:
                await self._generate_audio()
            
            logger.info(f"Loaded audio for source '{self.source.name}': {len(self.audio_data)} bytes")
            
        except Exception as e:
            logger.error(f"Error loading audio source '{self.source.name}': {e}")
            # Fallback to generated ring tone
            self.audio_data = AudioGenerator.generate_ring_tone(60.0, self.source.sample_rate)
    
    async def _load_from_file(self):
        """Load audio from file."""
        file_path = Path(self.source.path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {self.source.path}")
        
        if file_path.suffix.lower() == '.wav':
            await self._load_wav_file(file_path)
        else:
            raise ValueError(f"Unsupported audio format: {file_path.suffix}")
    
    async def _load_wav_file(self, file_path: Path):
        """Load WAV file."""
        try:
            with wave.open(str(file_path), 'rb') as wav_file:
                # Check format compatibility
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                
                logger.info(
                    f"WAV file info: {channels} channels, {sample_width} bytes/sample, "
                    f"{framerate} Hz"
                )
                
                # Read all frames
                frames = wav_file.readframes(wav_file.getnframes())
                
                # Convert if necessary
                if (framerate != self.source.sample_rate or 
                    channels != self.source.channels or 
                    sample_width != self.source.bits_per_sample // 8):
                    
                    frames = await self._convert_audio_format(
                        frames, channels, sample_width, framerate
                    )
                
                # Apply volume
                self.audio_data = self._apply_volume(frames, self.source.volume)
                
        except Exception as e:
            logger.error(f"Error loading WAV file: {e}")
            raise
    
    async def _convert_audio_format(self, audio_data: bytes, src_channels: int, 
                                  src_sample_width: int, src_sample_rate: int) -> bytes:
        """Convert audio format to target format."""
        # This is a simplified conversion - in production, use proper audio library
        logger.warning("Audio format conversion not fully implemented - using as-is")
        return audio_data
    
    def _apply_volume(self, audio_data: bytes, volume: float) -> bytes:
        """Apply volume adjustment to audio data."""
        if volume == 1.0:
            return audio_data
        
        # Convert bytes to samples, apply volume, convert back
        samples = []
        for i in range(0, len(audio_data), 2):
            if i + 1 < len(audio_data):
                sample = struct.unpack('<h', audio_data[i:i+2])[0]
                sample = int(sample * volume)
                sample = max(-32768, min(32767, sample))  # Clamp
                samples.append(struct.pack('<h', sample))
        
        return b''.join(samples)
    
    async def _load_from_stream(self):
        """Load audio from stream URL."""
        # This would implement streaming audio loading
        logger.warning("Stream loading not implemented - using generated audio")
        await self._generate_audio()
    
    async def _generate_audio(self):
        """Generate audio content."""
        # Generate 60 seconds of ring tone
        self.audio_data = AudioGenerator.generate_ring_tone(60.0, self.source.sample_rate)
    
    def get_next_chunk(self, chunk_size: int = 320) -> Optional[bytes]:
        """Get next audio chunk for playback."""
        if not self.audio_data or not self.is_playing:
            return None
        
        # Check if we've reached the end
        if self.position >= len(self.audio_data):
            if self.source.loop:
                self.position = 0
                self.loop_count += 1
                logger.debug(f"Looping audio source '{self.source.name}' (loop {self.loop_count})")
            else:
                self.is_playing = False
                return None
        
        # Get chunk
        end_pos = min(self.position + chunk_size, len(self.audio_data))
        chunk = self.audio_data[self.position:end_pos]
        self.position = end_pos
        
        # Pad chunk if necessary
        if len(chunk) < chunk_size and self.source.loop and len(self.audio_data) > 0:
            remaining = chunk_size - len(chunk)
            self.position = 0  # Reset for next iteration
            next_chunk = self.audio_data[:min(remaining, len(self.audio_data))]
            chunk += next_chunk
            self.position = len(next_chunk)
        
        return chunk
    
    def start(self):
        """Start playback."""
        self.is_playing = True
        logger.debug(f"Started playback for source '{self.source.name}'")
    
    def stop(self):
        """Stop playback."""
        self.is_playing = False
        logger.debug(f"Stopped playback for source '{self.source.name}'")
    
    def reset(self):
        """Reset playback position."""
        self.position = 0
        self.loop_count = 0


class MusicOnHoldManager:
    """Manager for Music on Hold functionality."""
    
    def __init__(self, call_manager=None, audio_bridge=None):
        self.call_manager = call_manager
        self.audio_bridge = audio_bridge
        
        # Music sources
        self.music_sources: Dict[str, MusicSource] = {}
        self.players: Dict[str, MusicPlayer] = {}  # call_id -> player
        
        # Active hold sessions
        self.hold_sessions: Dict[str, Dict[str, Any]] = {}  # call_id -> session info
        
        # Configuration
        self.default_source = "default_hold_music"
        self.chunk_size = 320  # 20ms at 8kHz, 16-bit mono
        self.playback_interval = 0.02  # 20ms
        
        # Statistics
        self.total_hold_sessions = 0
        self.active_sessions_count = 0
        
        # Playback task
        self._playback_task = None
        
        # Initialize default sources
        self._initialize_default_sources()
    
    def _initialize_default_sources(self):
        """Initialize default music sources."""
        # Default generated music
        default_source = MusicSource(
            name=self.default_source,
            source_type=MusicSourceType.GENERATED,
            loop=True,
            volume=0.6
        )
        self.add_music_source(default_source)
        
        # Ring tone source
        ring_source = MusicSource(
            name="ring_tone",
            source_type=MusicSourceType.GENERATED,
            loop=True,
            volume=0.8
        )
        self.add_music_source(ring_source)
    
    def add_music_source(self, source: MusicSource):
        """Add music source."""
        self.music_sources[source.name] = source
        logger.info(f"Added music source: {source.name} ({source.source_type.value})")
    
    def remove_music_source(self, name: str) -> bool:
        """Remove music source."""
        if name in self.music_sources:
            del self.music_sources[name]
            logger.info(f"Removed music source: {name}")
            return True
        return False
    
    async def start_hold_music(self, call_id: str, source_name: Optional[str] = None) -> bool:
        """Start music on hold for call."""
        try:
            if call_id in self.hold_sessions:
                logger.warning(f"Hold music already active for call {call_id}")
                return False
            
            # Use default source if not specified
            source_name = source_name or self.default_source
            
            if source_name not in self.music_sources:
                logger.error(f"Music source '{source_name}' not found")
                return False
            
            source = self.music_sources[source_name]
            
            # Create player
            player = MusicPlayer(source)
            await player._load_audio()  # Ensure audio is loaded
            
            # Start playback
            player.start()
            self.players[call_id] = player
            
            # Create hold session
            self.hold_sessions[call_id] = {
                "source_name": source_name,
                "start_time": time.time(),
                "total_chunks_sent": 0,
                "total_bytes_sent": 0
            }
            
            self.total_hold_sessions += 1
            self.active_sessions_count += 1
            
            # Start playback task if not running
            if not self._playback_task or self._playback_task.done():
                self._playback_task = asyncio.create_task(self._playback_loop())
            
            logger.info(f"Started hold music for call {call_id} with source '{source_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error starting hold music for call {call_id}: {e}")
            return False
    
    async def stop_hold_music(self, call_id: str) -> bool:
        """Stop music on hold for call."""
        try:
            if call_id not in self.hold_sessions:
                logger.warning(f"No hold music active for call {call_id}")
                return False
            
            # Stop player
            if call_id in self.players:
                self.players[call_id].stop()
                del self.players[call_id]
            
            # Remove session
            session = self.hold_sessions.pop(call_id)
            self.active_sessions_count -= 1
            
            duration = time.time() - session["start_time"]
            logger.info(
                f"Stopped hold music for call {call_id} - "
                f"Duration: {duration:.1f}s, Chunks: {session['total_chunks_sent']}, "
                f"Bytes: {session['total_bytes_sent']}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping hold music for call {call_id}: {e}")
            return False
    
    async def _playback_loop(self):
        """Main playback loop for hold music."""
        logger.info("Started music on hold playback loop")
        
        try:
            while self.players:
                start_time = time.time()
                
                # Process each active player
                for call_id in list(self.players.keys()):
                    try:
                        await self._process_player(call_id)
                    except Exception as e:
                        logger.error(f"Error processing player for call {call_id}: {e}")
                        # Remove problematic player
                        await self.stop_hold_music(call_id)
                
                # Sleep until next interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.playback_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
        except asyncio.CancelledError:
            logger.info("Music on hold playback loop cancelled")
        except Exception as e:
            logger.error(f"Error in music on hold playback loop: {e}")
        finally:
            logger.info("Music on hold playback loop ended")
    
    async def _process_player(self, call_id: str):
        """Process single player for audio chunk."""
        if call_id not in self.players or call_id not in self.hold_sessions:
            return
        
        player = self.players[call_id]
        session = self.hold_sessions[call_id]
        
        # Get next audio chunk
        chunk = player.get_next_chunk(self.chunk_size)
        
        if chunk:
            # Send audio to call
            success = await self._send_audio_to_call(call_id, chunk)
            
            if success:
                # Update statistics
                session["total_chunks_sent"] += 1
                session["total_bytes_sent"] += len(chunk)
            else:
                logger.warning(f"Failed to send audio chunk to call {call_id}")
        else:
            # Player finished (non-looping)
            logger.info(f"Hold music finished for call {call_id}")
            await self.stop_hold_music(call_id)
    
    async def _send_audio_to_call(self, call_id: str, audio_data: bytes) -> bool:
        """Send audio data to call."""
        try:
            if self.audio_bridge:
                # Send through audio bridge
                return await self.audio_bridge.send_audio_to_call(call_id, audio_data)
            else:
                # Log for testing
                logger.debug(f"Would send {len(audio_data)} bytes of hold music to call {call_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error sending audio to call {call_id}: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get music on hold statistics."""
        return {
            "total_hold_sessions": self.total_hold_sessions,
            "active_sessions": self.active_sessions_count,
            "configured_sources": len(self.music_sources),
            "active_players": len(self.players),
            "playback_task_running": bool(self._playback_task and not self._playback_task.done())
        }
    
    def get_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get active hold sessions."""
        current_time = time.time()
        
        return {
            call_id: {
                **session,
                "duration_seconds": current_time - session["start_time"],
                "source": self.music_sources[session["source_name"]].source_type.value
            }
            for call_id, session in self.hold_sessions.items()
        }
    
    def load_sources_from_config(self, config: List[Dict[str, Any]]):
        """Load music sources from configuration."""
        try:
            for source_config in config:
                source = MusicSource(
                    name=source_config["name"],
                    source_type=MusicSourceType(source_config["source_type"]),
                    path=source_config.get("path"),
                    url=source_config.get("url"),
                    loop=source_config.get("loop", True),
                    volume=source_config.get("volume", 0.8),
                    sample_rate=source_config.get("sample_rate", 8000),
                    channels=source_config.get("channels", 1),
                    bits_per_sample=source_config.get("bits_per_sample", 16)
                )
                self.add_music_source(source)
                
            logger.info(f"Loaded {len(config)} music sources from configuration")
            
        except Exception as e:
            logger.error(f"Error loading music sources: {e}")
            raise
    
    async def start(self):
        """Start the music on hold manager."""
        # Initialize the audio playback task if needed
        if not self._playback_task or self._playback_task.done():
            self._playback_task = asyncio.create_task(self._audio_playback_loop())
        logger.info("Music on hold manager started")
    
    async def stop(self):
        """Stop the music on hold manager."""
        # Stop all active sessions
        for call_id in list(self.hold_sessions.keys()):
            await self.stop_hold_music(call_id)
        
        # Cancel playback task
        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()
            try:
                await self._playback_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Music on hold manager stopped")
    
    async def _audio_playback_loop(self):
        """Background task for audio playback."""
        while True:
            try:
                await asyncio.sleep(self.playback_interval)
                
                # Process active sessions
                for call_id, session in list(self.hold_sessions.items()):
                    player = self.players.get(call_id)
                    if player and player.is_playing:
                        chunk = player.get_next_chunk(self.chunk_size)
                        if chunk and self.audio_bridge:
                            # Send audio to the call
                            await self.audio_bridge.send_audio(call_id, chunk)
                        elif not chunk:
                            # Player finished, stop session
                            await self.stop_hold_music(call_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in music playback loop: {e}")
                await asyncio.sleep(1.0)  # Brief pause before retrying
    
    async def cleanup(self):
        """Cleanup manager resources."""
        try:
            # Stop all hold sessions
            for call_id in list(self.hold_sessions.keys()):
                await self.stop_hold_music(call_id)
            
            # Cancel playback task
            if self._playback_task and not self._playback_task.done():
                self._playback_task.cancel()
                try:
                    await self._playback_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("Music on hold manager cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up music on hold manager: {e}")
"""Audio resampling utilities for SIP-AI integration."""
import numpy as np
from scipy import signal
import logging

logger = logging.getLogger(__name__)


class AudioResampler:
    """Handles audio resampling between different sample rates."""
    
    @staticmethod
    def resample_audio(audio_data: bytes, from_rate: int, to_rate: int, 
                      channels: int = 1, dtype=np.int16) -> bytes:
        """
        Resample audio data from one sample rate to another.
        
        Args:
            audio_data: Raw audio bytes
            from_rate: Source sample rate (e.g., 8000 for telephony)
            to_rate: Target sample rate (e.g., 16000 for AI STT)
            channels: Number of audio channels (1 for mono)
            dtype: Audio data type (int16 for 16-bit PCM)
            
        Returns:
            Resampled audio as bytes
        """
        if from_rate == to_rate:
            return audio_data
            
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=dtype)
            
            # Handle multi-channel audio
            if channels > 1:
                audio_array = audio_array.reshape(-1, channels)
                # For now, just use the first channel
                audio_array = audio_array[:, 0]
            
            # Calculate resampling ratio
            ratio = to_rate / from_rate
            
            # For common 8kHz to 16kHz (2x upsampling), use fast linear interpolation
            if from_rate == 8000 and to_rate == 16000:
                # Fast 2x upsampling with linear interpolation
                upsampled = np.zeros(len(audio_array) * 2, dtype=dtype)
                upsampled[::2] = audio_array
                upsampled[1::2] = audio_array  # Simple duplication for speed
                return upsampled.tobytes()
            
            # For 16kHz to 8kHz (2x downsampling), use simple decimation
            elif from_rate == 16000 and to_rate == 8000:
                # Fast 2x downsampling by taking every other sample
                downsampled = audio_array[::2]
                return downsampled.tobytes()
            
            # For other ratios, use scipy's resample (slower but high quality)
            else:
                num_samples = int(len(audio_array) * ratio)
                resampled = signal.resample(audio_array, num_samples)
                
                # Convert back to int16
                resampled = np.clip(resampled, -32768, 32767).astype(dtype)
                
                # Convert back to bytes
                return resampled.tobytes()
            
        except Exception as e:
            logger.error(f"Error resampling audio: {e}")
            # Return original if resampling fails
            return audio_data
    
    @staticmethod
    def downsample_simple(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Simple downsampling by decimation (faster but lower quality).
        Only works when from_rate is a multiple of to_rate.
        """
        if from_rate == to_rate:
            return audio_data
            
        if from_rate % to_rate != 0:
            # Fall back to high-quality resampling
            return AudioResampler.resample_audio(audio_data, from_rate, to_rate)
            
        try:
            decimation_factor = from_rate // to_rate
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Simple decimation
            downsampled = audio_array[::decimation_factor]
            
            return downsampled.tobytes()
            
        except Exception as e:
            logger.error(f"Error in simple downsampling: {e}")
            return audio_data
    
    @staticmethod
    def upsample_simple(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Simple upsampling by interpolation.
        """
        if from_rate == to_rate:
            return audio_data
            
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate upsampling factor
            factor = to_rate / from_rate
            
            if factor == 2.0:
                # Simple 2x upsampling with linear interpolation
                upsampled = np.zeros(len(audio_array) * 2 - 1, dtype=np.int16)
                upsampled[::2] = audio_array
                upsampled[1::2] = (audio_array[:-1] + audio_array[1:]) // 2
                return upsampled.tobytes()
            else:
                # Use high-quality resampling for other factors
                return AudioResampler.resample_audio(audio_data, from_rate, to_rate)
                
        except Exception as e:
            logger.error(f"Error in simple upsampling: {e}")
            return audio_data


class StreamingResampler:
    """Handles resampling for streaming audio with proper buffering."""
    
    def __init__(self, from_rate: int, to_rate: int, chunk_size: int = 320):
        """
        Initialize streaming resampler.
        
        Args:
            from_rate: Source sample rate
            to_rate: Target sample rate
            chunk_size: Expected input chunk size in bytes
        """
        self.from_rate = from_rate
        self.to_rate = to_rate
        self.chunk_size = chunk_size
        self.buffer = b""
        self.ratio = to_rate / from_rate
        
        # Calculate optimal processing size
        samples_per_chunk = chunk_size // 2  # 16-bit samples
        self.input_samples_needed = int(samples_per_chunk)
        self.output_samples = int(samples_per_chunk * self.ratio)
        
    def process_chunk(self, audio_chunk: bytes) -> bytes:
        """Process a chunk of audio data."""
        # Add to buffer
        self.buffer += audio_chunk
        
        output = b""
        
        # Process complete chunks
        while len(self.buffer) >= self.chunk_size:
            chunk = self.buffer[:self.chunk_size]
            self.buffer = self.buffer[self.chunk_size:]
            
            # Resample the chunk
            resampled = AudioResampler.resample_audio(
                chunk, self.from_rate, self.to_rate
            )
            output += resampled
            
        return output
    
    def flush(self) -> bytes:
        """Process any remaining buffered audio."""
        if not self.buffer:
            return b""
            
        # Process remaining buffer
        resampled = AudioResampler.resample_audio(
            self.buffer, self.from_rate, self.to_rate
        )
        self.buffer = b""
        return resampled
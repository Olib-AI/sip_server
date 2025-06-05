"""Media handling module for RTP bridge integration."""

# Import only what we need for the RTP bridge
from .codec_handler import CodecHandler, SupportedCodec

__all__ = [
    "CodecHandler",
    "SupportedCodec"
]
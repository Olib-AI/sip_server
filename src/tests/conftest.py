"""
Pytest configuration and shared fixtures for SIP server testing.
"""
import asyncio
import pytest
import pytest_asyncio
import logging
import os
import tempfile
import shutil
from typing import AsyncGenerator, Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import websockets
from websockets.legacy.server import WebSocketServerProtocol
from fastapi.testclient import TestClient
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import numpy as np

# Import project modules
from src.api.main import app
from src.call_handling.call_manager import CallManager, CallSession, CallState, CallDirection, CallPriority, CallParticipant
from src.websocket.bridge import WebSocketBridge
from src.audio.codecs import AudioProcessor
from src.audio.rtp import RTPManager
from src.dtmf.dtmf_detector import DTMFDetector
from src.dtmf.dtmf_processor import DTMFProcessor
from src.dtmf.ivr_manager import IVRManager
from src.dtmf.music_on_hold import MusicOnHoldManager
from src.sms.sms_manager import SMSManager
from src.utils.config import ConfigManager, get_config
from src.utils.sip_client import SIPClient
from src.models.database import get_db, init_db

# Configure test logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config():
    """Test configuration with realistic settings."""
    return {
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "sip_test_db",
            "user": "test_user",
            "password": "test_password",
            "url": "postgresql://test_user:test_password@localhost:5432/sip_test_db"
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8080,
            "cors_origins": ["*"]
        },
        "websocket": {
            "port": 8081,
            "ai_platform_url": "ws://localhost:8082/ws",
            "auth_required": True,
            "heartbeat_interval": 30
        },
        "sip": {
            "host": "localhost",
            "port": 5060,
            "domain": "test.sip.local",
            "transport": "UDP"
        },
        "audio": {
            "sample_rate": 8000,
            "frame_size": 160,
            "rtp_port_start": 10000,
            "rtp_port_end": 20000,
            "codecs": ["PCMU", "PCMA", "G722"]
        },
        "security": {
            "jwt_secret": "test_secret_key_12345678901234567890",
            "api_key": "test_api_key",
            "enable_auth": True
        },
        "call_manager": {
            "max_concurrent_calls": 100,
            "call_timeout": 300,
            "ring_timeout": 30
        }
    }


@pytest.fixture
def mock_config(test_config):
    """Mock configuration for testing."""
    config_manager = ConfigManager()
    
    # Mock all config attributes
    for key, value in test_config.items():
        setattr(config_manager, key, type('Config', (), value)())
    
    with patch('src.utils.config.get_config', return_value=config_manager):
        yield config_manager


@pytest.fixture
def test_database_url(test_config):
    """Test database URL."""
    return test_config["database"]["url"]


@pytest_asyncio.fixture
async def test_db_engine(test_database_url):
    """Test database engine with cleanup."""
    engine = create_engine(test_database_url, echo=False)
    
    # Create test database if it doesn't exist
    try:
        conn = engine.connect()
        conn.close()
    except Exception:
        # Create database
        admin_url = test_database_url.rsplit('/', 1)[0] + '/postgres'
        admin_engine = create_engine(admin_url)
        admin_conn = admin_engine.connect()
        admin_conn.execute("COMMIT")
        admin_conn.execute("CREATE DATABASE sip_test_db")
        admin_conn.close()
        admin_engine.dispose()
    
    yield engine
    
    # Cleanup
    engine.dispose()


@pytest.fixture
def mock_ai_websocket_manager():
    """Mock AI WebSocket manager for testing."""
    manager = AsyncMock()
    manager.send_message = AsyncMock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.is_connected = MagicMock(return_value=True)
    return manager


@pytest_asyncio.fixture
async def call_manager(mock_ai_websocket_manager, mock_config):
    """Create test call manager."""
    manager = CallManager(max_concurrent_calls=10, ai_websocket_manager=mock_ai_websocket_manager)
    await manager.start()
    yield manager
    await manager.stop()


@pytest_asyncio.fixture
async def websocket_bridge(mock_config):
    """Create test WebSocket bridge."""
    bridge = WebSocketBridge(
        ai_platform_url="ws://localhost:8082/ws",
        sip_ws_port=8081
    )
    yield bridge
    await bridge.stop()


@pytest.fixture
def audio_processor():
    """Create test audio processor."""
    return AudioProcessor()


@pytest_asyncio.fixture
async def rtp_manager():
    """Create test RTP manager."""
    manager = RTPManager(port_range=(10000, 11000))
    yield manager
    await manager.cleanup_all()


@pytest_asyncio.fixture
async def dtmf_detector():
    """Create test DTMF detector."""
    detector = DTMFDetector(enable_rfc2833=True, enable_inband=True)
    yield detector
    detector.cleanup()


@pytest_asyncio.fixture
async def dtmf_processor(mock_ai_websocket_manager, call_manager):
    """Create test DTMF processor."""
    processor = DTMFProcessor(mock_ai_websocket_manager, call_manager)
    await processor.start()
    yield processor
    await processor.stop()


@pytest_asyncio.fixture
async def ivr_manager(call_manager, dtmf_processor):
    """Create test IVR manager."""
    manager = IVRManager(call_manager, dtmf_processor)
    await manager.start()
    yield manager
    await manager.stop()


@pytest_asyncio.fixture
async def music_on_hold_manager(call_manager):
    """Create test music on hold manager."""
    manager = MusicOnHoldManager(call_manager)
    await manager.start()
    yield manager
    await manager.stop()


@pytest_asyncio.fixture
async def sms_manager(mock_ai_websocket_manager):
    """Create test SMS manager."""
    manager = SMSManager(ai_websocket_manager=mock_ai_websocket_manager)
    yield manager
    await manager.stop_processing()


@pytest.fixture
def sip_client(mock_config):
    """Create test SIP client."""
    return SIPClient()


@pytest.fixture
def api_client():
    """FastAPI test client."""
    return TestClient(app)


@pytest_asyncio.fixture
async def mock_websocket():
    """Mock WebSocket connection."""
    websocket = AsyncMock(spec=WebSocketServerProtocol)
    websocket.send = AsyncMock()
    websocket.recv = AsyncMock()
    websocket.close = AsyncMock()
    websocket.closed = False
    return websocket


@pytest.fixture
def sample_call_session():
    """Create sample call session for testing."""
    from datetime import datetime
    
    return CallSession(
        call_id="test-call-123",
        session_id="session-456",
        direction=CallDirection.INBOUND,
        state=CallState.INITIALIZING,
        priority=CallPriority.NORMAL,
        caller=CallParticipant(
            number="+12345678901",
            display_name="Test Caller",
            user_agent="Test UA",
            ip_address="192.168.1.100"
        ),
        callee=CallParticipant(
            number="+10987654321",
            display_name="Test Callee",
            is_registered=True
        ),
        created_at=datetime.utcnow(),
        codec="PCMU"
    )


@pytest.fixture
def sample_sip_data():
    """Sample SIP data for testing."""
    return {
        "call_id": "test-call-123",
        "sip_call_id": "sip-123@test.local",
        "from_number": "+12345678901",
        "to_number": "+10987654321",
        "caller_name": "Test Caller",
        "user_agent": "Test SIP Client",
        "remote_ip": "192.168.1.100",
        "headers": {
            "Contact": "<sip:test@192.168.1.100:5060>",
            "User-Agent": "Test SIP Client",
            "Content-Type": "application/sdp"
        }
    }


@pytest.fixture
def sample_audio_data():
    """Generate sample audio data for testing."""
    # Generate 20ms of 8kHz PCMU audio (160 samples)
    sample_rate = 8000
    duration = 0.02  # 20ms
    samples = int(sample_rate * duration)
    
    # Generate sine wave at 1kHz
    t = np.linspace(0, duration, samples, False)
    sine_wave = np.sin(2 * np.pi * 1000 * t)
    
    # Convert to 16-bit PCM
    pcm_data = (sine_wave * 32767).astype(np.int16).tobytes()
    
    return {
        "pcm": pcm_data,
        "pcmu": b'\x00' * 160,  # Mock PCMU data
        "pcma": b'\x55' * 160,  # Mock PCMA data
        "samples": samples,
        "sample_rate": sample_rate
    }


@pytest.fixture
def sample_rtp_packet():
    """Create sample RTP packet for testing."""
    # RTP header (12 bytes) + payload
    version = 2
    padding = 0
    extension = 0
    cc = 0
    marker = 0
    payload_type = 0  # PCMU
    sequence = 12345
    timestamp = 98765
    ssrc = 0x12345678
    
    header = bytearray(12)
    header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc
    header[1] = (marker << 7) | payload_type
    header[2:4] = sequence.to_bytes(2, 'big')
    header[4:8] = timestamp.to_bytes(4, 'big')
    header[8:12] = ssrc.to_bytes(4, 'big')
    
    payload = b'\x00' * 160  # PCMU payload
    
    return bytes(header) + payload


@pytest.fixture
def sample_dtmf_rtp_packet():
    """Create sample DTMF RTP packet (RFC 2833)."""
    # RTP header for DTMF
    version = 2
    padding = 0
    extension = 0
    cc = 0
    marker = 1  # Marker set for DTMF start
    payload_type = 101  # RFC 2833 DTMF
    sequence = 12346
    timestamp = 98766
    ssrc = 0x12345678
    
    header = bytearray(12)
    header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc
    header[1] = (marker << 7) | payload_type
    header[2:4] = sequence.to_bytes(2, 'big')
    header[4:8] = timestamp.to_bytes(4, 'big')
    header[8:12] = ssrc.to_bytes(4, 'big')
    
    # DTMF payload (digit '1')
    event = 1  # DTMF digit '1'
    end_volume = 0x00  # E=0, R=0, Volume=0
    duration = 800  # Duration in timestamp units
    
    dtmf_payload = bytearray(4)
    dtmf_payload[0] = event
    dtmf_payload[1] = end_volume
    dtmf_payload[2:4] = duration.to_bytes(2, 'big')
    
    return bytes(header) + bytes(dtmf_payload)


@pytest.fixture
def sample_sms_data():
    """Sample SMS data for testing."""
    return {
        "from_number": "+12345678901",
        "to_number": "+10987654321",
        "message": "Test SMS message with unicode 🚀",
        "timestamp": "2024-01-01T12:00:00Z",
        "message_id": "sms-123-456"
    }


@pytest_asyncio.fixture
async def mock_kamailio_rpc():
    """Mock Kamailio RPC server for testing."""
    responses = {
        "dlg.list": {"result": []},
        "dlg.profile_set": {"result": "ok"},
        "dlg.profile_unset": {"result": "ok"},
        "stats.set_stat": {"result": "ok"}
    }
    
    async def mock_post(url, json=None, timeout=None):
        method = json.get("method") if json else "unknown"
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(return_value=responses.get(method, {"error": "unknown method"}))
        return response
    
    with patch('aiohttp.ClientSession.post', mock_post):
        yield responses


@pytest.fixture
def temp_audio_file():
    """Create temporary audio file for testing."""
    temp_dir = tempfile.mkdtemp()
    audio_file = os.path.join(temp_dir, "test_audio.wav")
    
    # Create simple WAV file
    import wave
    with wave.open(audio_file, 'wb') as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(8000)  # 8kHz
        
        # Generate 1 second of sine wave
        samples = 8000
        t = np.linspace(0, 1, samples, False)
        sine_wave = np.sin(2 * np.pi * 440 * t)  # 440Hz A note
        audio_data = (sine_wave * 32767).astype(np.int16)
        wav.writeframes(audio_data.tobytes())
    
    yield audio_file
    
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def performance_thresholds():
    """Performance thresholds for testing."""
    return {
        "call_setup_time_ms": 100,
        "audio_latency_ms": 50,
        "websocket_response_ms": 10,
        "database_query_ms": 50,
        "api_response_ms": 200,
        "dtmf_detection_ms": 5,
        "codec_conversion_ms": 1,
        "concurrent_calls": 50
    }


# Test utilities

class TestUtils:
    """Utility functions for testing."""
    
    @staticmethod
    def generate_call_id() -> str:
        """Generate unique call ID."""
        import uuid
        return f"test-call-{uuid.uuid4()}"
    
    @staticmethod
    def generate_phone_number() -> str:
        """Generate random phone number."""
        import random
        return f"+1{random.randint(1000000000, 9999999999)}"
    
    @staticmethod
    async def wait_for_condition(condition_func, timeout: float = 5.0, interval: float = 0.1) -> bool:
        """Wait for condition to become true."""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await condition_func() if asyncio.iscoroutinefunction(condition_func) else condition_func():
                return True
            await asyncio.sleep(interval)
        
        return False
    
    @staticmethod
    def assert_audio_quality(audio_data: bytes, expected_duration: float, sample_rate: int = 8000):
        """Assert audio quality metrics."""
        expected_samples = int(expected_duration * sample_rate * 2)  # 16-bit samples
        assert len(audio_data) == expected_samples, f"Audio length mismatch: {len(audio_data)} vs {expected_samples}"
        
        # Check for silence (all zeros)
        assert not all(b == 0 for b in audio_data), "Audio data is all zeros (silence)"
    
    @staticmethod
    def create_mock_sip_message(method: str = "INVITE", call_id: str = None) -> Dict[str, Any]:
        """Create mock SIP message."""
        return {
            "method": method,
            "call_id": call_id or TestUtils.generate_call_id(),
            "from_number": TestUtils.generate_phone_number(),
            "to_number": TestUtils.generate_phone_number(),
            "headers": {
                "Contact": "<sip:test@192.168.1.100:5060>",
                "Content-Type": "application/sdp",
                "User-Agent": "Test SIP Client"
            },
            "body": "v=0\r\no=- 123456 654321 IN IP4 192.168.1.100\r\ns=-\r\nc=IN IP4 192.168.1.100\r\nt=0 0\r\nm=audio 5004 RTP/AVP 0\r\na=rtpmap:0 PCMU/8000\r\n"
        }


@pytest.fixture
def test_utils():
    """Test utilities fixture."""
    return TestUtils


# Global test markers
pytestmark = [
    pytest.mark.asyncio
]


# Test categories for selective running
pytest_plugins = [
    "pytest_asyncio",
    "pytest_mock"
]


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "load: Load tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "requires_docker: Tests requiring Docker")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location."""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        elif "load" in str(item.fspath):
            item.add_marker(pytest.mark.load)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
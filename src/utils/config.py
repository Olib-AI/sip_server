"""Configuration management for SIP server environment variables."""
import os
import logging
from typing import Optional, Dict, Any, Union
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    host: str = "postgres"
    port: int = 5432
    name: str = "kamailio"
    user: str = "kamailio"
    password: str = "kamailiopw"
    
    @property
    def url(self) -> str:
        """Generate database URL."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class SIPConfig:
    """SIP server configuration settings."""
    host: str = "0.0.0.0"
    port: int = 5060
    domain: str = "sip.olib.ai"
    proxy_address: str = "sip.olib.ai"
    proxy_port: int = 5060
    rtp_proxy_host: str = "127.0.0.1"
    rtp_proxy_port: int = 12221


@dataclass
class APIConfig:
    """API server configuration settings."""
    host: str = "0.0.0.0"
    port: int = 8080
    version: str = "1.0.0"


@dataclass
class WebSocketConfig:
    """WebSocket bridge configuration settings."""
    host: str = "0.0.0.0"
    port: int = 8081
    ai_platform_url: str = "ws://127.0.0.1:8081/ws"


@dataclass
class SecurityConfig:
    """Security and authentication configuration."""
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    api_key: str = "change-this-in-production"
    # Separate JWT secret for SIP user management (higher security)
    sip_jwt_secret: str = "change-this-sip-secret-in-production"
    # Shared secret for HMAC signatures with AI platform
    sip_shared_secret: str = "change-this-sip-shared-secret-in-production"


@dataclass
class CallConfig:
    """Call management configuration."""
    max_concurrent_calls: int = 1000
    default_codec: str = "PCMU"
    timeout_seconds: int = 300


@dataclass
class AudioConfig:
    """Audio processing configuration."""
    sample_rate: int = 8000
    frame_size: int = 160
    rtp_port_start: int = 10000
    rtp_port_end: int = 20000


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class DevConfig:
    """Development and testing configuration."""
    debug: bool = False
    testing: bool = False
    load_test_concurrent_calls: int = 100
    load_test_duration_seconds: int = 60


@dataclass
class MonitoringConfig:
    """Monitoring and health check configuration."""
    health_check_interval: int = 30
    metrics_enabled: bool = True
    prometheus_port: int = 9090
    grafana_port: int = 3000


@dataclass
class ExternalConfig:
    """External service configuration."""
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None


@dataclass
class AppConfig:
    """Main application configuration."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    sip: SIPConfig = field(default_factory=SIPConfig)
    api: APIConfig = field(default_factory=APIConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    call: CallConfig = field(default_factory=CallConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    dev: DevConfig = field(default_factory=DevConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    external: ExternalConfig = field(default_factory=ExternalConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary format for backwards compatibility."""
        return {
            "database": {
                "host": self.database.host,
                "port": self.database.port,
                "name": self.database.name,
                "user": self.database.user,
                "password": self.database.password,
                "url": self.database.url
            },
            "call_manager": {
                "max_concurrent_calls": self.call.max_concurrent_calls,
                "default_codec": self.call.default_codec,
                "timeout_seconds": self.call.timeout_seconds
            },
            "websocket": {
                "ai_platform_url": self.websocket.ai_platform_url,
                "port": self.websocket.port,
                "host": self.websocket.host
            },
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "version": self.api.version
            },
            "sip": {
                "host": self.sip.host,
                "port": self.sip.port,
                "domain": self.sip.domain,
                "rtp_proxy_host": self.sip.rtp_proxy_host,
                "rtp_proxy_port": self.sip.rtp_proxy_port
            },
            "security": {
                "jwt_secret_key": self.security.jwt_secret_key,
                "jwt_algorithm": self.security.jwt_algorithm,
                "jwt_expire_minutes": self.security.jwt_expire_minutes,
                "api_key": self.security.api_key,
                "sip_shared_secret": self.security.sip_shared_secret
            },
            "audio": {
                "sample_rate": self.audio.sample_rate,
                "frame_size": self.audio.frame_size,
                "rtp_port_start": self.audio.rtp_port_start,
                "rtp_port_end": self.audio.rtp_port_end
            },
            "logging": {
                "level": self.logging.level,
                "format": self.logging.format
            },
            "dev": {
                "debug": self.dev.debug,
                "testing": self.dev.testing
            },
            "monitoring": {
                "health_check_interval": self.monitoring.health_check_interval,
                "metrics_enabled": self.monitoring.metrics_enabled,
                "prometheus_port": self.monitoring.prometheus_port,
                "grafana_port": self.monitoring.grafana_port
            },
            "external": {
                "twilio_account_sid": self.external.twilio_account_sid,
                "twilio_auth_token": self.external.twilio_auth_token
            }
        }


class ConfigManager:
    """Configuration manager that loads settings from environment variables."""
    
    def __init__(self, env_file: Optional[str] = None):
        """Initialize configuration manager.
        
        Args:
            env_file: Path to .env file (optional)
        """
        self.env_file = env_file
        self._load_env_file()
        
    def _load_env_file(self):
        """Load environment variables from .env file if it exists."""
        if self.env_file and os.path.exists(self.env_file):
            self._load_dotenv(self.env_file)
        else:
            # Try to find .env file in common locations
            possible_paths = [
                ".env",
                "../.env",
                "../../.env",
                os.path.join(Path(__file__).parent.parent.parent, ".env")
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self._load_dotenv(path)
                    break
    
    def _load_dotenv(self, filepath: str):
        """Load environment variables from a .env file."""
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and not os.environ.get(key):
                            os.environ[key] = value
            logger.info(f"Loaded environment variables from {filepath}")
        except Exception as e:
            logger.warning(f"Failed to load .env file {filepath}: {e}")
    
    def _get_env(self, key: str, default: Any = None, cast_type: type = str) -> Any:
        """Get environment variable with optional type casting."""
        value = os.environ.get(key)
        
        if value is None:
            return default
            
        if cast_type == bool:
            if isinstance(value, bool):
                return value
            return str(value).lower() in ('true', '1', 'yes', 'on')
        elif cast_type == int:
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        elif cast_type == float:
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        else:
            return str(value)
    
    def load_config(self) -> AppConfig:
        """Load configuration from environment variables."""
        
        # Database configuration
        database = DatabaseConfig(
            host=self._get_env("DB_HOST", "postgres"),
            port=self._get_env("DB_PORT", 5432, int),
            name=self._get_env("DB_NAME", "kamailio"),
            user=self._get_env("DB_USER", "kamailio"),
            password=self._get_env("DB_PASSWORD", "kamailiopw")
        )
        
        # SIP configuration
        sip = SIPConfig(
            host=self._get_env("SIP_HOST", "0.0.0.0"),
            port=self._get_env("SIP_PORT", 5060, int),
            domain=self._get_env("SIP_DOMAIN", "sip.olib.ai"),
            proxy_address=self._get_env("SIP_PROXY_ADDRESS", "sip.olib.ai"),
            proxy_port=self._get_env("SIP_PROXY_PORT", 5060, int),
            rtp_proxy_host=self._get_env("RTP_PROXY_HOST", "127.0.0.1"),
            rtp_proxy_port=self._get_env("RTP_PROXY_PORT", 12221, int)
        )
        
        # API configuration
        api = APIConfig(
            host=self._get_env("API_HOST", "0.0.0.0"),
            port=self._get_env("API_PORT", 8080, int),
            version=self._get_env("API_VERSION", "1.0.0")
        )
        
        # WebSocket configuration
        websocket = WebSocketConfig(
            host=self._get_env("WEBSOCKET_HOST", "0.0.0.0"),
            port=self._get_env("WEBSOCKET_PORT", 8081, int),
            ai_platform_url=self._get_env("AI_PLATFORM_WS_URL", "ws://127.0.0.1:8081/ws")
        )
        
        # Security configuration
        security = SecurityConfig(
            jwt_secret_key=self._get_env("JWT_SECRET_KEY", "change-this-in-production"),
            jwt_algorithm=self._get_env("JWT_ALGORITHM", "HS256"),
            jwt_expire_minutes=self._get_env("JWT_EXPIRE_MINUTES", 30, int),
            api_key=self._get_env("API_KEY", "change-this-in-production"),
            sip_jwt_secret=self._get_env("SIP_JWT_SECRET", "change-this-sip-secret-in-production"),
            sip_shared_secret=self._get_env("SIP_SHARED_SECRET", "change-this-sip-shared-secret-in-production")
        )
        
        # Call management configuration
        call = CallConfig(
            max_concurrent_calls=self._get_env("MAX_CONCURRENT_CALLS", 1000, int),
            default_codec=self._get_env("DEFAULT_CODEC", "PCMU"),
            timeout_seconds=self._get_env("CALL_TIMEOUT_SECONDS", 300, int)
        )
        
        # Audio configuration
        audio = AudioConfig(
            sample_rate=self._get_env("AUDIO_SAMPLE_RATE", 8000, int),
            frame_size=self._get_env("AUDIO_FRAME_SIZE", 160, int),
            rtp_port_start=self._get_env("RTP_PORT_RANGE_START", 10000, int),
            rtp_port_end=self._get_env("RTP_PORT_RANGE_END", 20000, int)
        )
        
        # Logging configuration
        logging_config = LoggingConfig(
            level=self._get_env("LOG_LEVEL", "INFO"),
            format=self._get_env("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        
        # Development configuration
        dev = DevConfig(
            debug=self._get_env("DEBUG", False, bool),
            testing=self._get_env("TESTING", False, bool),
            load_test_concurrent_calls=self._get_env("LOAD_TEST_CONCURRENT_CALLS", 100, int),
            load_test_duration_seconds=self._get_env("LOAD_TEST_DURATION_SECONDS", 60, int)
        )
        
        # Monitoring configuration
        monitoring = MonitoringConfig(
            health_check_interval=self._get_env("HEALTH_CHECK_INTERVAL", 30, int),
            metrics_enabled=self._get_env("METRICS_ENABLED", True, bool),
            prometheus_port=self._get_env("PROMETHEUS_PORT", 9090, int),
            grafana_port=self._get_env("GRAFANA_PORT", 3000, int)
        )
        
        # External services configuration
        external = ExternalConfig(
            twilio_account_sid=self._get_env("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=self._get_env("TWILIO_AUTH_TOKEN")
        )
        
        return AppConfig(
            database=database,
            sip=sip,
            api=api,
            websocket=websocket,
            security=security,
            call=call,
            audio=audio,
            logging=logging_config,
            dev=dev,
            monitoring=monitoring,
            external=external
        )


# Global configuration instance
_config_manager = None
_app_config = None


def get_config_manager(env_file: Optional[str] = None) -> ConfigManager:
    """Get global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(env_file)
    return _config_manager


def get_config(env_file: Optional[str] = None) -> AppConfig:
    """Get global application configuration."""
    global _app_config
    if _app_config is None:
        config_manager = get_config_manager(env_file)
        _app_config = config_manager.load_config()
    return _app_config


def reload_config(env_file: Optional[str] = None) -> AppConfig:
    """Reload configuration from environment."""
    global _config_manager, _app_config
    _config_manager = ConfigManager(env_file)
    _app_config = _config_manager.load_config()
    return _app_config


# Convenience functions for backwards compatibility
def get_database_url() -> str:
    """Get database URL from configuration."""
    return get_config().database.url


def get_api_config() -> Dict[str, Any]:
    """Get API configuration dictionary."""
    config = get_config()
    return {
        "host": config.api.host,
        "port": config.api.port,
        "version": config.api.version
    }


def get_websocket_config() -> Dict[str, Any]:
    """Get WebSocket configuration dictionary."""
    config = get_config()
    return {
        "host": config.websocket.host,
        "port": config.websocket.port,
        "ai_platform_url": config.websocket.ai_platform_url
    }
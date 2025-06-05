"""Tests for configuration system."""
import pytest
import os
import tempfile
from unittest.mock import patch

from ..utils.config import ConfigManager, get_config, reload_config


class TestConfigManager:
    """Test configuration management."""
    
    def test_default_config_values(self):
        """Test default configuration values."""
        # Clear environment to test defaults
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager().load_config()
            
            assert config.database.host == "postgres"
            assert config.database.port == 5432
            assert config.api.port == 8080
            assert config.websocket.port == 8081
            assert config.sip.port == 5060
    
    def test_env_var_override(self):
        """Test environment variable override."""
        test_env = {
            'DB_HOST': 'test-db',
            'DB_PORT': '3306',
            'API_PORT': '9090',
            'JWT_SECRET_KEY': 'test-secret'
        }
        
        with patch.dict(os.environ, test_env):
            config = ConfigManager().load_config()
            
            assert config.database.host == "test-db"
            assert config.database.port == 3306
            assert config.api.port == 9090
            assert config.security.jwt_secret_key == "test-secret"
    
    def test_env_file_loading(self):
        """Test .env file loading."""
        # Create temporary .env file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("DB_HOST=env-file-db\n")
            f.write("API_PORT=7777\n")
            f.write("LOG_LEVEL=DEBUG\n")
            env_file_path = f.name
        
        try:
            config_manager = ConfigManager(env_file_path)
            config = config_manager.load_config()
            
            assert config.database.host == "env-file-db"
            assert config.api.port == 7777
            assert config.logging.level == "DEBUG"
        finally:
            os.unlink(env_file_path)
    
    def test_database_url_generation(self):
        """Test database URL generation."""
        test_env = {
            'DB_HOST': 'test-host',
            'DB_PORT': '5432',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        }
        
        with patch.dict(os.environ, test_env):
            config = ConfigManager().load_config()
            expected_url = "postgresql://test-user:test-pass@test-host:5432/test-db"
            assert config.database.url == expected_url
    
    def test_boolean_env_vars(self):
        """Test boolean environment variable parsing."""
        test_cases = [
            ('true', True),
            ('True', True),
            ('1', True),
            ('yes', True),
            ('on', True),
            ('false', False),
            ('False', False),
            ('0', False),
            ('no', False),
            ('off', False),
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {'DEBUG': env_value}):
                config = ConfigManager().load_config()
                assert config.dev.debug == expected
    
    def test_config_dict_compatibility(self):
        """Test backward compatibility with dict format."""
        config = get_config()
        config_dict = config.to_dict()
        
        # Test that all expected keys are present
        assert "database" in config_dict
        assert "api" in config_dict
        assert "websocket" in config_dict
        assert "sip" in config_dict
        assert "security" in config_dict
        
        # Test nested structure
        assert "host" in config_dict["database"]
        assert "port" in config_dict["api"]
        assert "jwt_secret_key" in config_dict["security"]


class TestConfigIntegration:
    """Test configuration integration."""
    
    def test_config_reload(self):
        """Test configuration reload functionality."""
        # Set initial environment
        with patch.dict(os.environ, {'API_PORT': '8080'}):
            config1 = get_config()
            assert config1.api.port == 8080
        
        # Change environment and reload
        with patch.dict(os.environ, {'API_PORT': '9090'}):
            config2 = reload_config()
            assert config2.api.port == 9090
    
    def test_global_config_singleton(self):
        """Test that global config is singleton."""
        config1 = get_config()
        config2 = get_config()
        
        # Should be the same instance
        assert config1 is config2


@pytest.fixture
def clean_env():
    """Fixture to provide clean environment for tests."""
    original_env = os.environ.copy()
    # Clear all our config-related env vars
    config_vars = [
        'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD',
        'API_HOST', 'API_PORT', 'WEBSOCKET_HOST', 'WEBSOCKET_PORT',
        'SIP_HOST', 'SIP_PORT', 'JWT_SECRET_KEY', 'LOG_LEVEL', 'DEBUG'
    ]
    
    for var in config_vars:
        os.environ.pop(var, None)
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
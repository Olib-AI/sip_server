"""Unit tests for trunk management functionality."""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from ...models.database import TrunkConfiguration
from ...models.schemas import TrunkCreate, TrunkUpdate, TrunkInfo
from ...api.routes.trunks import encrypt_password, decrypt_password


class TestTrunkPasswordEncryption:
    """Test trunk password encryption/decryption."""
    
    def test_encrypt_password_valid(self):
        """Test password encryption with valid input."""
        password = "test_password_123"
        encrypted = encrypt_password(password)
        
        assert encrypted != password
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0
    
    def test_encrypt_password_empty(self):
        """Test password encryption with empty input."""
        result = encrypt_password("")
        assert result == ""
        
        result = encrypt_password(None)
        assert result == ""
    
    def test_decrypt_password_valid(self):
        """Test password decryption with valid input."""
        password = "test_password_123"
        encrypted = encrypt_password(password)
        decrypted = decrypt_password(encrypted)
        
        assert decrypted == password
    
    def test_decrypt_password_empty(self):
        """Test password decryption with empty input."""
        result = decrypt_password("")
        assert result == ""
        
        result = decrypt_password(None)
        assert result == ""
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test encrypt/decrypt roundtrip maintains data integrity."""
        passwords = [
            "simple_password",
            "complex_p@ssw0rd!",
            "unicode_password_€£¥",
            "very_long_password_" * 10
        ]
        
        for password in passwords:
            encrypted = encrypt_password(password)
            decrypted = decrypt_password(encrypted)
            assert decrypted == password


class TestTrunkSchemas:
    """Test trunk Pydantic schemas."""
    
    def test_trunk_create_valid(self):
        """Test TrunkCreate schema with valid data."""
        trunk_data = {
            "trunk_id": "test_trunk",
            "name": "Test Trunk",
            "provider": "skyetel",
            "proxy_address": "sip.skyetel.com",
            "proxy_port": 5060,
            "username": "test_user",
            "password": "test_pass",
            "realm": "sip.skyetel.com",
            "transport": "UDP",
            "supports_outbound": True,
            "supports_inbound": True,
            "preferred_codecs": ["PCMU", "PCMA"],
            "max_concurrent_calls": 100
        }
        
        trunk = TrunkCreate(**trunk_data)
        assert trunk.trunk_id == "test_trunk"
        assert trunk.name == "Test Trunk"
        assert trunk.provider == "skyetel"
        assert trunk.proxy_address == "sip.skyetel.com"
        assert trunk.proxy_port == 5060
        assert trunk.preferred_codecs == ["PCMU", "PCMA"]
    
    def test_trunk_create_invalid_trunk_id(self):
        """Test TrunkCreate with invalid trunk_id."""
        trunk_data = {
            "trunk_id": "invalid trunk id",  # spaces not allowed
            "name": "Test Trunk",
            "provider": "skyetel",
            "proxy_address": "sip.skyetel.com"
        }
        
        with pytest.raises(ValueError, match="Trunk ID must contain only alphanumeric"):
            TrunkCreate(**trunk_data)
    
    def test_trunk_create_invalid_transport(self):
        """Test TrunkCreate with invalid transport."""
        trunk_data = {
            "trunk_id": "test_trunk",
            "name": "Test Trunk", 
            "provider": "skyetel",
            "proxy_address": "sip.skyetel.com",
            "transport": "INVALID"
        }
        
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TrunkCreate(**trunk_data)
    
    def test_trunk_create_defaults(self):
        """Test TrunkCreate with default values."""
        trunk_data = {
            "trunk_id": "test_trunk",
            "name": "Test Trunk",
            "provider": "skyetel", 
            "proxy_address": "sip.skyetel.com"
        }
        
        trunk = TrunkCreate(**trunk_data)
        assert trunk.proxy_port == 5060
        assert trunk.registrar_port == 5060
        assert trunk.transport == "UDP"
        assert trunk.auth_method == "digest"
        assert trunk.supports_registration == True
        assert trunk.supports_outbound == True
        assert trunk.supports_inbound == True
        assert trunk.preferred_codecs == ["PCMU", "PCMA"]
        assert trunk.enable_dtmf_relay == True
        assert trunk.max_concurrent_calls == 100
    
    def test_trunk_update_partial(self):
        """Test TrunkUpdate with partial data."""
        update_data = {
            "name": "Updated Trunk Name",
            "max_concurrent_calls": 200
        }
        
        trunk_update = TrunkUpdate(**update_data)
        assert trunk_update.name == "Updated Trunk Name"
        assert trunk_update.max_concurrent_calls == 200
        assert trunk_update.provider is None  # Not provided
        assert trunk_update.proxy_address is None  # Not provided
    
    def test_trunk_info_from_db_model(self):
        """Test TrunkInfo creation from database model."""
        # Mock database model
        db_trunk = Mock()
        db_trunk.id = 1
        db_trunk.trunk_id = "test_trunk"
        db_trunk.name = "Test Trunk"
        db_trunk.provider = "skyetel"
        db_trunk.proxy_address = "sip.skyetel.com"
        db_trunk.proxy_port = 5060
        db_trunk.registrar_address = None
        db_trunk.registrar_port = 5060
        db_trunk.username = "test_user"
        db_trunk.realm = "sip.skyetel.com"
        db_trunk.auth_method = "digest"
        db_trunk.transport = "UDP"
        db_trunk.supports_registration = True
        db_trunk.supports_outbound = True
        db_trunk.supports_inbound = True
        db_trunk.dial_prefix = ""
        db_trunk.strip_digits = 0
        db_trunk.prepend_digits = ""
        db_trunk.max_concurrent_calls = 100
        db_trunk.calls_per_second_limit = 10
        db_trunk.preferred_codecs = ["PCMU", "PCMA"]
        db_trunk.enable_dtmf_relay = True
        db_trunk.rtp_timeout = 60
        db_trunk.heartbeat_interval = 30
        db_trunk.registration_expire = 3600
        db_trunk.failover_timeout = 30
        db_trunk.backup_trunks = []
        db_trunk.allowed_ips = []
        db_trunk.status = "active"
        db_trunk.failure_count = 0
        db_trunk.last_registration = None
        db_trunk.total_calls = 0
        db_trunk.successful_calls = 0
        db_trunk.failed_calls = 0
        db_trunk.current_calls = 0
        db_trunk.created_at = datetime.now(timezone.utc)
        db_trunk.updated_at = datetime.now(timezone.utc)
        
        trunk_info = TrunkInfo(
            id=db_trunk.id,
            trunk_id=db_trunk.trunk_id,
            name=db_trunk.name,
            provider=db_trunk.provider,
            proxy_address=db_trunk.proxy_address,
            proxy_port=db_trunk.proxy_port,
            registrar_address=db_trunk.registrar_address,
            registrar_port=db_trunk.registrar_port,
            username=db_trunk.username,
            realm=db_trunk.realm,
            auth_method=db_trunk.auth_method,
            transport=db_trunk.transport,
            supports_registration=db_trunk.supports_registration,
            supports_outbound=db_trunk.supports_outbound,
            supports_inbound=db_trunk.supports_inbound,
            dial_prefix=db_trunk.dial_prefix,
            strip_digits=db_trunk.strip_digits,
            prepend_digits=db_trunk.prepend_digits,
            max_concurrent_calls=db_trunk.max_concurrent_calls,
            calls_per_second_limit=db_trunk.calls_per_second_limit,
            preferred_codecs=db_trunk.preferred_codecs,
            enable_dtmf_relay=db_trunk.enable_dtmf_relay,
            rtp_timeout=db_trunk.rtp_timeout,
            heartbeat_interval=db_trunk.heartbeat_interval,
            registration_expire=db_trunk.registration_expire,
            failover_timeout=db_trunk.failover_timeout,
            backup_trunks=db_trunk.backup_trunks,
            allowed_ips=db_trunk.allowed_ips,
            status=db_trunk.status,
            failure_count=db_trunk.failure_count,
            last_registration=db_trunk.last_registration,
            total_calls=db_trunk.total_calls,
            successful_calls=db_trunk.successful_calls,
            failed_calls=db_trunk.failed_calls,
            current_calls=db_trunk.current_calls,
            created_at=db_trunk.created_at,
            updated_at=db_trunk.updated_at
        )
        
        assert trunk_info.id == 1
        assert trunk_info.trunk_id == "test_trunk"
        assert trunk_info.name == "Test Trunk"
        assert trunk_info.provider == "skyetel"
        assert trunk_info.status == "active"


class TestTrunkDatabaseModel:
    """Test TrunkConfiguration database model."""
    
    def test_trunk_model_creation(self):
        """Test creating TrunkConfiguration model."""
        now = datetime.now(timezone.utc)
        
        trunk = TrunkConfiguration(
            trunk_id="test_trunk",
            name="Test Trunk",
            provider="skyetel",
            proxy_address="sip.skyetel.com",
            proxy_port=5060,
            username="test_user",
            password="encrypted_password",
            realm="sip.skyetel.com",
            auth_method="digest",
            transport="UDP",
            supports_registration=True,
            supports_outbound=True,
            supports_inbound=True,
            preferred_codecs=["PCMU", "PCMA"],
            max_concurrent_calls=100,
            status="inactive",
            total_calls=0,
            successful_calls=0,
            failed_calls=0,
            current_calls=0,
            created_at=now,
            updated_at=now
        )
        
        assert trunk.trunk_id == "test_trunk"
        assert trunk.name == "Test Trunk"
        assert trunk.provider == "skyetel"
        assert trunk.proxy_address == "sip.skyetel.com"
        assert trunk.proxy_port == 5060
        assert trunk.username == "test_user"
        assert trunk.password == "encrypted_password"
        assert trunk.preferred_codecs == ["PCMU", "PCMA"]
        assert trunk.status == "inactive"
        assert trunk.total_calls == 0
        assert trunk.successful_calls == 0
        assert trunk.failed_calls == 0
        assert trunk.current_calls == 0
    
    def test_trunk_model_defaults(self):
        """Test TrunkConfiguration model with default values."""
        # SQLAlchemy defaults are applied when the object is saved to DB,
        # not when the object is created in memory
        trunk = TrunkConfiguration(
            trunk_id="test_trunk",
            name="Test Trunk", 
            provider="skyetel",
            proxy_address="sip.skyetel.com"
        )
        
        # Test that required fields are set
        assert trunk.trunk_id == "test_trunk"
        assert trunk.name == "Test Trunk"
        assert trunk.provider == "skyetel"
        assert trunk.proxy_address == "sip.skyetel.com"
        
        # For SQLAlchemy defaults, we need to check the column defaults
        table = TrunkConfiguration.__table__
        
        assert table.c.proxy_port.default.arg == 5060
        assert table.c.registrar_port.default.arg == 5060
        assert table.c.auth_method.default.arg == "digest"
        assert table.c.transport.default.arg == "UDP"
        assert table.c.supports_registration.default.arg == True
        assert table.c.supports_outbound.default.arg == True
        assert table.c.supports_inbound.default.arg == True
        assert table.c.max_concurrent_calls.default.arg == 100
        assert table.c.calls_per_second_limit.default.arg == 10
        assert table.c.status.default.arg == "inactive"


class TestTrunkUtilities:
    """Test trunk utility functions."""
    
    def test_trunk_id_validation(self):
        """Test trunk ID validation logic."""
        valid_ids = [
            "skyetel_main",
            "trunk-1",
            "provider123",
            "backup_trunk_2"
        ]
        
        for trunk_id in valid_ids:
            # This should not raise an error
            trunk_data = {
                "trunk_id": trunk_id,
                "name": "Test Trunk",
                "provider": "test",
                "proxy_address": "sip.test.com"
            }
            trunk = TrunkCreate(**trunk_data)
            assert trunk.trunk_id == trunk_id.lower()
    
    def test_trunk_id_invalid_chars(self):
        """Test trunk ID with invalid characters."""
        invalid_ids = [
            "trunk with spaces",
            "trunk@provider.com",
            "trunk#1",
            "trunk/backup"
        ]
        
        for trunk_id in invalid_ids:
            trunk_data = {
                "trunk_id": trunk_id,
                "name": "Test Trunk",
                "provider": "test",
                "proxy_address": "sip.test.com"
            }
            with pytest.raises(ValueError):
                TrunkCreate(**trunk_data)
    
    def test_codec_list_validation(self):
        """Test codec list validation."""
        valid_codecs = [
            ["PCMU"],
            ["PCMA"],
            ["PCMU", "PCMA"],
            ["PCMU", "PCMA", "G729"],
            []  # Empty list should be allowed
        ]
        
        for codecs in valid_codecs:
            trunk_data = {
                "trunk_id": "test_trunk",
                "name": "Test Trunk",
                "provider": "test",
                "proxy_address": "sip.test.com",
                "preferred_codecs": codecs
            }
            trunk = TrunkCreate(**trunk_data)
            assert trunk.preferred_codecs == codecs
    
    def test_port_validation(self):
        """Test port number validation."""
        # Valid ports
        valid_ports = [1024, 5060, 5061, 65535]
        
        for port in valid_ports:
            trunk_data = {
                "trunk_id": "test_trunk",
                "name": "Test Trunk",
                "provider": "test",
                "proxy_address": "sip.test.com",
                "proxy_port": port
            }
            trunk = TrunkCreate(**trunk_data)
            assert trunk.proxy_port == port
        
        # Invalid ports should raise validation error
        invalid_ports = [0, -1, 65536, 100000]
        
        for port in invalid_ports:
            trunk_data = {
                "trunk_id": "test_trunk",
                "name": "Test Trunk",
                "provider": "test",
                "proxy_address": "sip.test.com",
                "proxy_port": port
            }
            with pytest.raises(ValueError):
                TrunkCreate(**trunk_data)
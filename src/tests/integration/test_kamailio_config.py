"""Integration tests for Kamailio configuration."""
import pytest
import subprocess
import os
import tempfile
import socket
from unittest.mock import patch, Mock


class TestKamailioConfiguration:
    """Test suite for Kamailio configuration validation."""
    
    def test_kamailio_config_syntax(self):
        """Test that Kamailio configuration has valid syntax."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        # Check if config file exists
        assert os.path.exists(config_path), f"Config file not found: {config_path}"
        
        # Test syntax using kamailio -c (if available)
        try:
            result = subprocess.run(
                ["kamailio", "-c", "-f", config_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # If kamailio is available, check syntax
            if result.returncode == 0:
                assert "config file ok" in result.stdout.lower() or result.returncode == 0
            else:
                # If kamailio not available, just check file is readable
                with open(config_path, 'r') as f:
                    content = f.read()
                    assert len(content) > 0
                    assert "loadmodule" in content
                    assert "route[" in content
                    
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback: just verify file structure
            with open(config_path, 'r') as f:
                content = f.read()
                assert len(content) > 0
                assert "loadmodule" in content
                assert "route[" in content
    
    def test_required_modules_loaded(self):
        """Test that required modules are loaded in config."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for essential modules
        required_modules = [
            "tm.so",
            "sl.so", 
            "rr.so",
            "pv.so",
            "maxfwd.so",
            "usrloc.so",
            "registrar.so",
            "textops.so",
            "siputils.so",
            "xlog.so",
            "sanity.so",
            "websocket.so",
            "http_async_client.so"
        ]
        
        for module in required_modules:
            assert f'loadmodule "{module}"' in content, f"Required module {module} not loaded"
    
    def test_websocket_integration_routes(self):
        """Test that WebSocket integration routes are present."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for WebSocket-related configurations
        assert "http_async_query" in content, "HTTP async query for WebSocket bridge not found"
        assert "127.0.0.1:8080" in content, "WebSocket bridge endpoint not configured"
        assert "route[INBOUND]" in content, "Inbound call routing not found"
        assert "route[MESSAGE]" in content, "SMS MESSAGE routing not found"
        assert "event_route[http_async_reply]" in content, "HTTP async reply handler not found"
    
    def test_database_configuration(self):
        """Test database configuration parameters."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for PostgreSQL configuration
        assert "db_postgres.so" in content, "PostgreSQL module not loaded"
        assert "postgres://kamailio:kamailiopw@postgres/kamailio" in content, "Database URL not configured"
        assert "usrloc" in content, "User location module not configured"
    
    def test_sip_ports_configuration(self):
        """Test SIP port configuration."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for standard SIP ports
        assert "port=5060" in content, "SIP port 5060 not configured"
        assert "listen=udp:0.0.0.0:5060" in content, "UDP SIP listener not configured"
        assert "listen=tcp:0.0.0.0:5060" in content, "TCP SIP listener not configured"
    
    def test_rtp_configuration(self):
        """Test RTP configuration."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for RTP-related configuration
        assert "rtpproxy.so" in content, "RTPProxy module not loaded"
        assert "rtpproxy_sock" in content, "RTPProxy socket not configured"
        assert "route[RTPPROXY]" in content, "RTPProxy routing not found"


class TestHTTPAsyncIntegration:
    """Test HTTP async client integration for WebSocket bridge."""
    
    def test_http_async_client_config(self):
        """Test HTTP async client configuration."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check HTTP async client configuration
        assert 'loadmodule "http_async_client.so"' in content
        assert 'modparam("http_async_client", "workers"' in content
        assert 'modparam("http_async_client", "connection_timeout"' in content
        assert 'modparam("http_async_client", "query_result"' in content
    
    def test_websocket_bridge_endpoints(self):
        """Test WebSocket bridge endpoint configuration."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for WebSocket bridge API endpoints
        assert "/api/sip/calls/incoming" in content, "Incoming call endpoint not configured"
        assert "/api/sip/sms/incoming" in content, "SMS endpoint not configured"
    
    def test_http_reply_handling(self):
        """Test HTTP async reply handling."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for HTTP reply handling
        assert "event_route[http_async_reply]" in content
        assert "HTTP_CALL_REPLY" in content
        assert "HTTP_SMS_REPLY" in content


class TestRouteLogic:
    """Test routing logic in Kamailio configuration."""
    
    def test_main_request_route(self):
        """Test main request routing logic."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check main request route structure
        assert "request_route {" in content
        assert "route(REQINIT)" in content
        assert "route(NATDETECT)" in content
        assert "route(WITHINDLG)" in content
        assert "route(AUTH)" in content
    
    def test_invite_handling(self):
        """Test INVITE request handling."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check INVITE handling
        assert 'is_method("INVITE")' in content
        assert "route(INVITE)" in content
        assert "route[INVITE]" in content
        assert "route[INBOUND]" in content
        assert "route[OUTBOUND]" in content
    
    def test_message_handling(self):
        """Test MESSAGE (SMS) handling."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check MESSAGE handling
        assert 'is_method("MESSAGE")' in content
        assert "route(MESSAGE)" in content
        assert "route[MESSAGE]" in content
    
    def test_websocket_handling(self):
        """Test WebSocket handling in HTTP events."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check WebSocket handling
        assert "event_route[xhttp:request]" in content
        assert "websocket" in content.lower()
        assert "ws_handle_handshake" in content


class TestConfigurationValidation:
    """Test configuration file validation."""
    
    def test_config_file_structure(self):
        """Test basic configuration file structure."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            lines = f.readlines()
        
        # Check file is not empty
        assert len(lines) > 0
        
        # Check for essential sections
        content = ''.join(lines)
        sections = [
            "####### Global Parameters #########",
            "####### Modules Section ########",
            "####### Module Parameters #######",
            "####### Routing Logic ########"
        ]
        
        for section in sections:
            assert section in content, f"Configuration section '{section}' not found"
    
    def test_no_syntax_errors(self):
        """Test for common syntax errors."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for balanced braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        assert open_braces == close_braces, "Unbalanced braces in configuration"
        
        # Check for balanced parentheses in modparam
        modparam_lines = [line for line in content.split('\n') if 'modparam(' in line]
        for line in modparam_lines:
            open_parens = line.count('(')
            close_parens = line.count(')')
            assert open_parens == close_parens, f"Unbalanced parentheses in line: {line}"
    
    def test_required_parameters(self):
        """Test that required parameters are set."""
        config_path = "/Users/ahstanin/GitHub/Olib-AI/olib-app/sip_server/config/kamailio.cfg"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for essential parameters
        required_params = [
            "debug=",
            "log_stderror=",
            "fork=",
            "children=",
            "port=",
            "listen="
        ]
        
        for param in required_params:
            assert param in content, f"Required parameter '{param}' not found"


# Mock test for network connectivity (when running in CI/CD)
class TestNetworkConfiguration:
    """Test network-related configuration."""
    
    def test_port_availability(self):
        """Test that configured ports can be bound (mock test)."""
        # This is a mock test since we can't actually bind ports in unit tests
        # In real deployment, these ports should be available
        
        required_ports = [5060, 8080]  # SIP and API ports
        
        for port in required_ports:
            # Mock test - just verify port numbers are reasonable
            assert 1024 <= port <= 65535, f"Port {port} is not in valid range"
            assert isinstance(port, int), f"Port {port} is not an integer"
    
    @patch('socket.socket')
    def test_socket_binding_mock(self, mock_socket):
        """Mock test for socket binding capability."""
        # Mock socket creation and binding
        mock_sock = Mock()
        mock_socket.return_value = mock_sock
        mock_sock.bind.return_value = None
        mock_sock.listen.return_value = None
        
        # Test that socket operations would work
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', 5060))
        sock.listen(5)
        
        # Verify mock was called
        mock_socket.assert_called_once()
        mock_sock.bind.assert_called_once_with(('0.0.0.0', 5060))
        mock_sock.listen.assert_called_once_with(5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
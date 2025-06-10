"""Main integration script for SIP server with AI platform."""
import asyncio
import logging
import signal
import sys
from typing import Optional
import json
import os

from .call_handling.call_manager import CallManager
from .call_handling.websocket_integration import WebSocketCallBridge
from .api.sip_integration import initialize_services, start_api_server
from .utils.config import get_config, AppConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('sip_integration.log')
    ]
)

logger = logging.getLogger(__name__)


class SIPIntegrationServer:
    """Main SIP integration server."""
    
    def __init__(self, config_path: Optional[str] = None, env_file: Optional[str] = None):
        self.app_config = get_config(env_file)
        self.config = self.app_config.to_dict()  # For backwards compatibility
        self.call_manager: Optional[CallManager] = None
        self.websocket_bridge: Optional[WebSocketCallBridge] = None
        self.api_server_task: Optional[asyncio.Task] = None
        self.websocket_task: Optional[asyncio.Task] = None
        self.permanent_rtp_session = None
        self.is_running = False
        
        # Override with JSON config file if provided
        if config_path:
            self._load_json_config(config_path)
        
        # Configure logging based on loaded config
        self._configure_logging()
        logger.info(f"Configuration loaded from environment variables")
        
    def _load_json_config(self, config_path: str):
        """Load and merge JSON configuration file."""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    file_config = json.load(f)
                    # Merge with environment config
                    self._merge_config(self.config, file_config)
                logger.info(f"Merged configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
    
    def _merge_config(self, base: dict, override: dict):
        """Recursively merge configuration dictionaries."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _configure_logging(self):
        """Configure logging based on configuration."""
        log_level = getattr(logging, self.app_config.logging.level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format=self.app_config.logging.format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('sip_integration.log')
            ],
            force=True  # Reconfigure logging
        )
    
    async def _start_permanent_rtp_listener(self):
        """Start a permanent RTP listener on port 10000 for incoming calls."""
        try:
            from .audio.rtp import RTPSession
            
            # Create permanent RTP session for port 10000
            self.permanent_rtp_session = RTPSession(
                local_port=10000,
                remote_host="",  # Will be set when we receive RTP
                remote_port=0,  # Will be set when we receive RTP
                payload_type=0,  # PCMU
                codec="PCMU"
            )
            
            # Set up callback to route audio to appropriate call
            def permanent_audio_callback(audio_data: bytes, remote_addr=None):
                logger.info(f"🎵 Permanent RTP listener received {len(audio_data)} bytes")
                # Update remote address for outgoing packets if we got a new one
                if remote_addr and (not self.permanent_rtp_session.remote_host or 
                                   remote_addr[0] != self.permanent_rtp_session.remote_host or 
                                   remote_addr[1] != self.permanent_rtp_session.remote_port):
                    logger.info(f"🎯 Updating RTP remote address to {remote_addr}")
                    self.permanent_rtp_session.remote_host = remote_addr[0]
                    self.permanent_rtp_session.remote_port = remote_addr[1]
                
                # Route to active call via WebSocket bridge
                if self.websocket_bridge:
                    asyncio.create_task(
                        self.websocket_bridge._route_rtp_to_active_call(audio_data, remote_addr)
                    )
            
            self.permanent_rtp_session.set_receive_callback(permanent_audio_callback)
            
            # Start the permanent session
            await self.permanent_rtp_session.start()
            
            if self.permanent_rtp_session.running:
                logger.info("✅ Permanent RTP listener started on port 10000")
            else:
                logger.error("❌ Failed to start permanent RTP listener on port 10000")
                
        except Exception as e:
            logger.error(f"❌ Error starting permanent RTP listener: {e}")
            import traceback
            traceback.print_exc()
    
    async def start(self):
        """Start all services."""
        try:
            logger.info("Starting SIP Integration Server...")
            self.is_running = True
            
            # Initialize call manager
            logger.info("Initializing call manager...")
            self.call_manager = CallManager(
                max_concurrent_calls=self.config["call_manager"]["max_concurrent_calls"]
            )
            
            # Load call manager configuration
            if "call_manager_config" in self.config:
                self.call_manager.load_configuration(self.config["call_manager_config"])
            
            # Initialize WebSocket bridge
            logger.info("Initializing WebSocket bridge...")
            self.websocket_bridge = WebSocketCallBridge(
                call_manager=self.call_manager,
                ai_websocket_url=self.config["websocket"]["ai_platform_url"],
                port=self.config["websocket"]["port"]
            )
            
            # Initialize API services
            logger.info("Initializing API services...")
            initialize_services(self.call_manager, self.websocket_bridge)
            
            # Start WebSocket bridge
            logger.info("Starting WebSocket bridge...")
            await self.websocket_bridge.start()
            
            # Start permanent RTP listener on port 10000
            logger.info("Starting permanent RTP listener...")
            await self._start_permanent_rtp_listener()
            
            # Connect permanent RTP session to WebSocket bridge
            if self.permanent_rtp_session and self.websocket_bridge:
                self.websocket_bridge.set_permanent_rtp_session(self.permanent_rtp_session)
            
            # Start API server
            logger.info("Starting API server...")
            self.api_server_task = asyncio.create_task(
                start_api_server(
                    host=self.config["api"]["host"],
                    port=self.config["api"]["port"]
                )
            )
            
            logger.info("SIP Integration Server started successfully")
            logger.info(f"API server listening on {self.config['api']['host']}:{self.config['api']['port']}")
            logger.info(f"WebSocket bridge on port {self.config['websocket']['port']}")
            
            # Wait for tasks to complete
            await asyncio.gather(
                self.api_server_task,
                return_exceptions=True
            )
            
        except Exception as e:
            logger.error(f"Failed to start SIP Integration Server: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop all services."""
        try:
            logger.info("Stopping SIP Integration Server...")
            self.is_running = False
            
            # Stop API server
            if self.api_server_task and not self.api_server_task.done():
                logger.info("Stopping API server...")
                self.api_server_task.cancel()
                try:
                    await self.api_server_task
                except asyncio.CancelledError:
                    pass
            
            # Stop WebSocket bridge
            if self.websocket_bridge:
                logger.info("Stopping WebSocket bridge...")
                await self.websocket_bridge.stop()
            
            # Stop permanent RTP listener
            if hasattr(self, 'permanent_rtp_session') and self.permanent_rtp_session:
                logger.info("Stopping permanent RTP listener...")
                await self.permanent_rtp_session.stop()
            
            # Cleanup call manager
            if self.call_manager:
                logger.info("Cleaning up call manager...")
                await self.call_manager.cleanup()
            
            logger.info("SIP Integration Server stopped")
            
        except Exception as e:
            logger.error(f"Error stopping SIP Integration Server: {e}")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SIP Integration Server")
    parser.add_argument("--config", help="JSON configuration file path")
    parser.add_argument("--env-file", help="Environment file path (.env)")
    parser.add_argument("--log-level", help="Logging level (overrides env config)")
    args = parser.parse_args()
    
    # Create and start server
    server = SIPIntegrationServer(config_path=args.config, env_file=args.env_file)
    
    # Override log level if provided via command line
    if args.log_level:
        log_level = getattr(logging, args.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
    
    # Suppress websockets connection errors (they're just health checks)
    websockets_logger = logging.getLogger('websockets.server')
    websockets_logger.setLevel(logging.CRITICAL)
    
    server.setup_signal_handlers()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
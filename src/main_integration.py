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
        # No permanent RTP session - using individual sessions per call
        self.is_running = False
        
        # Override with JSON config file if provided
        if config_path:
            self._load_json_config(config_path)
        
        # Configure logging based on loaded config
        self._configure_logging()
        logger.info(f"Configuration loaded - Ready for concurrent call handling")
        
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
    
    # Removed permanent RTP listener - now using individual RTP sessions per call
    # This method is no longer needed as each call gets its own RTP session
    async def _start_individual_call_handling(self):
        """Initialize individual call handling system (replaces permanent RTP listener)."""
        try:
            logger.info("🎧 Individual call handling system initialized")
            logger.info("✅ Ready to create individual RTP sessions for each call")
                
        except Exception as e:
            logger.error(f"❌ Error initializing call handling system: {e}")
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
            
            # Initialize individual call handling system
            logger.info("Initializing individual call handling system...")
            await self._start_individual_call_handling()
            
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
            logger.info(f"Ready for concurrent calls with individual RTP sessions")
            
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
                # Cleanup all active calls before stopping
                for call_id in list(self.websocket_bridge.call_rtp_sessions.keys()):
                    await self.websocket_bridge._force_cleanup_call(call_id)
                await self.websocket_bridge.stop()
            
            # No permanent RTP listener to stop - individual sessions are cleaned up by WebSocket bridge
            logger.info("Individual call handling system will be cleaned up by WebSocket bridge...")
            
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
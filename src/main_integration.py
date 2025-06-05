"""Main integration script for SIP server with AI platform."""
import asyncio
import logging
import signal
import sys
from typing import Optional
import json
import os

from call_handling.call_manager import CallManager
from call_handling.websocket_integration import WebSocketCallBridge
from api.sip_integration import initialize_services, start_api_server

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
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.call_manager: Optional[CallManager] = None
        self.websocket_bridge: Optional[WebSocketCallBridge] = None
        self.api_server_task: Optional[asyncio.Task] = None
        self.websocket_task: Optional[asyncio.Task] = None
        self.is_running = False
        
    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "call_manager": {
                "max_concurrent_calls": 1000,
                "default_codec": "PCMU"
            },
            "websocket": {
                "ai_platform_url": "ws://127.0.0.1:8080/ws",
                "port": 8080
            },
            "api": {
                "host": "0.0.0.0",
                "port": 8080
            },
            "logging": {
                "level": "INFO"
            }
        }
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    file_config = json.load(f)
                    # Merge with defaults
                    default_config.update(file_config)
                logger.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")
        else:
            logger.info("Using default configuration")
        
        return default_config
    
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
                ai_websocket_url=self.config["websocket"]["ai_platform_url"]
            )
            
            # Initialize API services
            logger.info("Initializing API services...")
            initialize_services(self.call_manager, self.websocket_bridge)
            
            # Start WebSocket bridge
            logger.info("Starting WebSocket bridge...")
            await self.websocket_bridge.start()
            
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
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # Create and start server
    server = SIPIntegrationServer(config_path=args.config)
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
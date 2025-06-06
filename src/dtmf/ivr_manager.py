"""Interactive Voice Response (IVR) System."""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .dtmf_detector import DTMFEvent
from .music_on_hold import MusicOnHoldManager, AudioGenerator

logger = logging.getLogger(__name__)


class IVRPromptType(Enum):
    """IVR prompt types."""
    AUDIO_FILE = "audio_file"
    TEXT_TO_SPEECH = "text_to_speech"
    GENERATED_TONE = "generated_tone"
    SILENCE = "silence"


class IVRActionType(Enum):
    """IVR action types."""
    TRANSFER_CALL = "transfer_call"
    PLAY_PROMPT = "play_prompt"
    GOTO_MENU = "goto_menu"
    HANGUP_CALL = "hangup_call"
    FORWARD_TO_AI = "forward_to_ai"
    COLLECT_INPUT = "collect_input"
    REPEAT_MENU = "repeat_menu"
    PREVIOUS_MENU = "previous_menu"
    CUSTOM_HANDLER = "custom_handler"


@dataclass
class IVRPrompt:
    """IVR prompt configuration."""
    prompt_id: str
    prompt_type: IVRPromptType
    content: str  # File path, TTS text, or tone specification
    duration_seconds: Optional[float] = None
    volume: float = 0.8
    repeat_count: int = 1
    interruptible: bool = True
    
    # TTS settings
    tts_voice: str = "default"
    tts_speed: float = 1.0
    
    # Generated tone settings
    tone_frequency: Optional[float] = None
    tone_amplitude: float = 0.3


@dataclass
class IVRAction:
    """IVR action configuration."""
    action_type: IVRActionType
    target: Optional[str] = None  # Transfer number, menu ID, etc.
    prompt: Optional[IVRPrompt] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    custom_handler: Optional[str] = None


@dataclass
class IVRMenuItem:
    """IVR menu item."""
    digit: str
    description: str
    action: IVRAction
    enabled: bool = True


@dataclass
class IVRMenu:
    """IVR menu configuration."""
    menu_id: str
    name: str
    welcome_prompt: IVRPrompt
    timeout_seconds: float = 10.0
    max_retries: int = 3
    invalid_prompt: Optional[IVRPrompt] = None
    timeout_prompt: Optional[IVRPrompt] = None
    timeout_action: Optional[IVRAction] = None
    invalid_action: Optional[IVRAction] = None
    
    # Menu items
    items: Dict[str, IVRMenuItem] = field(default_factory=dict)
    
    def add_item(self, item: IVRMenuItem):
        """Add menu item."""
        self.items[item.digit] = item
    
    def get_item(self, digit: str) -> Optional[IVRMenuItem]:
        """Get menu item by digit."""
        return self.items.get(digit)
    
    def get_enabled_items(self) -> Dict[str, IVRMenuItem]:
        """Get enabled menu items."""
        return {digit: item for digit, item in self.items.items() if item.enabled}


@dataclass
class IVRSession:
    """Active IVR session."""
    call_id: str
    current_menu_id: str
    session_id: str
    start_time: float
    menu_stack: List[str] = field(default_factory=list)  # For navigation history
    collected_input: str = ""
    retry_count: int = 0
    last_prompt_time: float = 0.0
    waiting_for_input: bool = False
    current_prompt: Optional[IVRPrompt] = None
    
    def push_menu(self, menu_id: str):
        """Push current menu to stack and set new menu."""
        if self.current_menu_id:
            self.menu_stack.append(self.current_menu_id)
        self.current_menu_id = menu_id
        self.retry_count = 0
    
    def pop_menu(self) -> Optional[str]:
        """Pop previous menu from stack."""
        if self.menu_stack:
            self.current_menu_id = self.menu_stack.pop()
            self.retry_count = 0
            return self.current_menu_id
        return None


class AudioPlayer:
    """Audio player for IVR prompts."""
    
    def __init__(self, audio_bridge=None):
        self.audio_bridge = audio_bridge
        self.active_playbacks: Dict[str, Dict] = {}  # call_id -> playback info
    
    async def play_prompt(self, call_id: str, prompt: IVRPrompt) -> bool:
        """Play IVR prompt to call."""
        try:
            logger.info(f"Playing IVR prompt '{prompt.prompt_id}' to call {call_id}")
            
            # Generate or load audio data
            audio_data = await self._prepare_audio(prompt)
            
            if not audio_data:
                logger.error(f"Failed to prepare audio for prompt '{prompt.prompt_id}'")
                return False
            
            # Store playback info
            self.active_playbacks[call_id] = {
                "prompt": prompt,
                "audio_data": audio_data,
                "position": 0,
                "start_time": time.time(),
                "repeat_count": 0
            }
            
            # Start playback
            success = await self._start_playback(call_id)
            
            return success
            
        except Exception as e:
            logger.error(f"Error playing IVR prompt: {e}")
            return False
    
    async def stop_prompt(self, call_id: str) -> bool:
        """Stop prompt playback for call."""
        try:
            if call_id in self.active_playbacks:
                del self.active_playbacks[call_id]
                logger.debug(f"Stopped IVR prompt playback for call {call_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error stopping IVR prompt: {e}")
            return False
    
    async def _prepare_audio(self, prompt: IVRPrompt) -> Optional[bytes]:
        """Prepare audio data for prompt."""
        try:
            if prompt.prompt_type == IVRPromptType.AUDIO_FILE:
                return await self._load_audio_file(prompt.content)
            
            elif prompt.prompt_type == IVRPromptType.TEXT_TO_SPEECH:
                return await self._generate_tts(prompt)
            
            elif prompt.prompt_type == IVRPromptType.GENERATED_TONE:
                return await self._generate_tone(prompt)
            
            elif prompt.prompt_type == IVRPromptType.SILENCE:
                duration = prompt.duration_seconds or 1.0
                return AudioGenerator.generate_silence(duration)
            
            else:
                logger.error(f"Unknown prompt type: {prompt.prompt_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error preparing audio for prompt: {e}")
            return None
    
    async def _load_audio_file(self, file_path: str) -> Optional[bytes]:
        """Load audio from file."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"Audio file not found: {file_path}")
                return None
            
            # For now, assume WAV files (would need proper audio library)
            with open(path, 'rb') as f:
                # Skip WAV header (44 bytes) - simplified
                f.seek(44)
                return f.read()
                
        except Exception as e:
            logger.error(f"Error loading audio file '{file_path}': {e}")
            return None
    
    async def _generate_tts(self, prompt: IVRPrompt) -> Optional[bytes]:
        """Generate text-to-speech audio."""
        # This would integrate with TTS service
        logger.warning(f"TTS not implemented - generating tone for: {prompt.content}")
        return AudioGenerator.generate_tone(800, 2.0)
    
    async def _generate_tone(self, prompt: IVRPrompt) -> Optional[bytes]:
        """Generate tone audio."""
        frequency = prompt.tone_frequency or 800
        duration = prompt.duration_seconds or 1.0
        amplitude = prompt.tone_amplitude
        
        return AudioGenerator.generate_tone(frequency, duration, amplitude=amplitude)
    
    async def _start_playback(self, call_id: str) -> bool:
        """Start audio playback for call."""
        if self.audio_bridge:
            # Would implement actual audio streaming
            return True
        else:
            # Simulate playback
            logger.info(f"Simulating audio playback for call {call_id}")
            return True


class IVRManager:
    """Main IVR manager."""
    
    def __init__(self, call_manager=None, audio_bridge=None, dtmf_processor=None):
        self.call_manager = call_manager
        self.audio_bridge = audio_bridge
        self.dtmf_processor = dtmf_processor
        
        # IVR configuration
        self.menus: Dict[str, IVRMenu] = {}
        self.active_sessions: Dict[str, IVRSession] = {}
        
        # Components
        self.audio_player = AudioPlayer(audio_bridge)
        
        # Custom handlers
        self.custom_handlers: Dict[str, Callable] = {}
        
        # Statistics
        self.total_sessions = 0
        self.completed_sessions = 0
        self.failed_sessions = 0
        
        # Configuration
        self.default_menu_id = "main_menu"
        self.session_timeout = 300  # 5 minutes
        
        # Cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        
        # Register DTMF handler
        if self.dtmf_processor:
            self.dtmf_processor.add_event_handler(self._handle_dtmf_event)
    
    def add_menu(self, menu: IVRMenu):
        """Add IVR menu."""
        self.menus[menu.menu_id] = menu
        logger.info(f"Added IVR menu: {menu.menu_id} ({menu.name})")
    
    def remove_menu(self, menu_id: str) -> bool:
        """Remove IVR menu."""
        if menu_id in self.menus:
            del self.menus[menu_id]
            logger.info(f"Removed IVR menu: {menu_id}")
            return True
        return False
    
    def add_custom_handler(self, name: str, handler: Callable):
        """Add custom IVR handler."""
        self.custom_handlers[name] = handler
        logger.info(f"Added custom IVR handler: {name}")
    
    async def start_ivr_session(self, call_id: str, menu_id: Optional[str] = None) -> bool:
        """Start IVR session for call."""
        try:
            if call_id in self.active_sessions:
                logger.warning(f"IVR session already active for call {call_id}")
                return False
            
            # Use default menu if not specified
            menu_id = menu_id or self.default_menu_id
            
            if menu_id not in self.menus:
                logger.error(f"IVR menu '{menu_id}' not found")
                return False
            
            # Create session
            session = IVRSession(
                call_id=call_id,
                current_menu_id=menu_id,
                session_id=f"ivr_{int(time.time())}_{call_id}",
                start_time=time.time()
            )
            
            self.active_sessions[call_id] = session
            self.total_sessions += 1
            
            # Start with welcome prompt
            success = await self._present_menu(call_id, menu_id)
            
            if success:
                logger.info(f"Started IVR session for call {call_id} with menu '{menu_id}'")
            else:
                await self.end_ivr_session(call_id, "failed_to_start")
            
            return success
            
        except Exception as e:
            logger.error(f"Error starting IVR session for call {call_id}: {e}")
            return False
    
    async def end_ivr_session(self, call_id: str, reason: str = "normal") -> bool:
        """End IVR session for call."""
        try:
            if call_id not in self.active_sessions:
                return False
            
            session = self.active_sessions.pop(call_id)
            
            # Stop any active audio
            await self.audio_player.stop_prompt(call_id)
            
            # Update statistics
            if reason == "completed":
                self.completed_sessions += 1
            elif reason in ["failed", "timeout", "failed_to_start"]:
                self.failed_sessions += 1
            
            duration = time.time() - session.start_time
            logger.info(f"Ended IVR session for call {call_id}: {reason} (duration: {duration:.1f}s)")
            
            return True
            
        except Exception as e:
            logger.error(f"Error ending IVR session for call {call_id}: {e}")
            return False
    
    async def _handle_dtmf_event(self, event: DTMFEvent):
        """Handle DTMF event for IVR."""
        call_id = event.call_id
        
        if call_id not in self.active_sessions:
            return  # Not in IVR session
        
        session = self.active_sessions[call_id]
        
        try:
            # Stop current prompt if interruptible
            menu = self.menus.get(session.current_menu_id)
            if menu and session.current_prompt and session.current_prompt.interruptible:
                await self.audio_player.stop_prompt(call_id)
            
            # Process digit
            await self._process_menu_input(call_id, event.digit)
            
        except Exception as e:
            logger.error(f"Error handling DTMF in IVR for call {call_id}: {e}")
    
    async def _present_menu(self, call_id: str, menu_id: str) -> bool:
        """Present IVR menu to caller."""
        try:
            menu = self.menus.get(menu_id)
            if not menu:
                logger.error(f"Menu '{menu_id}' not found")
                return False
            
            session = self.active_sessions[call_id]
            session.current_menu_id = menu_id
            session.waiting_for_input = True
            session.last_prompt_time = time.time()
            session.current_prompt = menu.welcome_prompt
            
            # Play welcome prompt
            success = await self.audio_player.play_prompt(call_id, menu.welcome_prompt)
            
            if success:
                # Start input timeout
                asyncio.create_task(self._handle_input_timeout(call_id, menu.timeout_seconds))
            
            return success
            
        except Exception as e:
            logger.error(f"Error presenting menu '{menu_id}' to call {call_id}: {e}")
            return False
    
    async def _process_menu_input(self, call_id: str, digit: str):
        """Process menu input digit."""
        session = self.active_sessions[call_id]
        menu = self.menus[session.current_menu_id]
        
        # Get menu item
        item = menu.get_item(digit)
        
        if item and item.enabled:
            # Valid input - execute action
            session.retry_count = 0
            await self._execute_action(call_id, item.action)
        else:
            # Invalid input
            session.retry_count += 1
            
            if session.retry_count >= menu.max_retries:
                # Max retries reached
                if menu.timeout_action:
                    await self._execute_action(call_id, menu.timeout_action)
                else:
                    await self.end_ivr_session(call_id, "max_retries")
            else:
                # Play invalid prompt and retry
                if menu.invalid_prompt:
                    await self.audio_player.play_prompt(call_id, menu.invalid_prompt)
                
                # Wait for next input
                session.waiting_for_input = True
                session.last_prompt_time = time.time()
                asyncio.create_task(self._handle_input_timeout(call_id, menu.timeout_seconds))
    
    async def _execute_action(self, call_id: str, action: IVRAction):
        """Execute IVR action."""
        try:
            action_type = action.action_type
            
            if action_type == IVRActionType.TRANSFER_CALL:
                await self._transfer_call(call_id, action.target)
            
            elif action_type == IVRActionType.PLAY_PROMPT:
                if action.prompt:
                    await self.audio_player.play_prompt(call_id, action.prompt)
            
            elif action_type == IVRActionType.GOTO_MENU:
                session = self.active_sessions[call_id]
                session.push_menu(action.target)
                await self._present_menu(call_id, action.target)
            
            elif action_type == IVRActionType.HANGUP_CALL:
                await self._hangup_call(call_id)
            
            elif action_type == IVRActionType.FORWARD_TO_AI:
                await self._forward_to_ai(call_id, action.parameters)
            
            elif action_type == IVRActionType.COLLECT_INPUT:
                await self._collect_input(call_id, action.parameters)
            
            elif action_type == IVRActionType.REPEAT_MENU:
                await self._present_menu(call_id, self.active_sessions[call_id].current_menu_id)
            
            elif action_type == IVRActionType.PREVIOUS_MENU:
                session = self.active_sessions[call_id]
                previous_menu = session.pop_menu()
                if previous_menu:
                    await self._present_menu(call_id, previous_menu)
                else:
                    await self.end_ivr_session(call_id, "no_previous_menu")
            
            elif action_type == IVRActionType.CUSTOM_HANDLER:
                await self._execute_custom_handler(call_id, action)
            
            else:
                logger.warning(f"Unknown IVR action type: {action_type}")
                
        except Exception as e:
            logger.error(f"Error executing IVR action {action_type}: {e}")
    
    async def _transfer_call(self, call_id: str, target: str):
        """Transfer call and end IVR session."""
        if self.call_manager:
            success = await self.call_manager.transfer_call(call_id, target, "blind")
            if success:
                await self.end_ivr_session(call_id, "transferred")
            else:
                await self.end_ivr_session(call_id, "transfer_failed")
    
    async def _hangup_call(self, call_id: str):
        """Hang up call and end IVR session."""
        if self.call_manager:
            await self.call_manager.hangup_call(call_id, "ivr_hangup")
        await self.end_ivr_session(call_id, "hung_up")
    
    async def _forward_to_ai(self, call_id: str, parameters: Dict[str, Any]):
        """Forward call to AI and end IVR session."""
        # This would integrate with AI system
        logger.info(f"Forwarding call {call_id} to AI with parameters: {parameters}")
        await self.end_ivr_session(call_id, "forwarded_to_ai")
    
    async def _collect_input(self, call_id: str, parameters: Dict[str, Any]):
        """Start input collection mode."""
        session = self.active_sessions[call_id]
        session.collected_input = ""
        session.waiting_for_input = True
        
        # This would implement digit collection with specific rules
        logger.info(f"Starting input collection for call {call_id}: {parameters}")
    
    async def _execute_custom_handler(self, call_id: str, action: IVRAction):
        """Execute custom handler."""
        handler_name = action.custom_handler
        if handler_name and handler_name in self.custom_handlers:
            handler = self.custom_handlers[handler_name]
            
            if asyncio.iscoroutinefunction(handler):
                await handler(call_id, action.parameters)
            else:
                handler(call_id, action.parameters)
    
    async def _handle_input_timeout(self, call_id: str, timeout_seconds: float):
        """Handle input timeout for IVR menu."""
        await asyncio.sleep(timeout_seconds)
        
        # Check if still waiting for input
        if call_id in self.active_sessions:
            session = self.active_sessions[call_id]
            if session.waiting_for_input:
                session.waiting_for_input = False
                
                menu = self.menus.get(session.current_menu_id)
                if menu:
                    session.retry_count += 1
                    
                    if session.retry_count >= menu.max_retries:
                        # Max retries reached
                        if menu.timeout_action:
                            await self._execute_action(call_id, menu.timeout_action)
                        else:
                            await self.end_ivr_session(call_id, "timeout")
                    else:
                        # Play timeout prompt and retry
                        if menu.timeout_prompt:
                            await self.audio_player.play_prompt(call_id, menu.timeout_prompt)
                        else:
                            await self._present_menu(call_id, session.current_menu_id)
    
    async def _cleanup_expired_sessions(self):
        """Cleanup expired IVR sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = time.time()
                expired_calls = []
                
                for call_id, session in self.active_sessions.items():
                    if (current_time - session.start_time) > self.session_timeout:
                        expired_calls.append(call_id)
                
                for call_id in expired_calls:
                    logger.info(f"Cleaning up expired IVR session for call {call_id}")
                    await self.end_ivr_session(call_id, "session_timeout")
                    
            except Exception as e:
                logger.error(f"Error in IVR cleanup task: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get IVR statistics."""
        return {
            "total_sessions": self.total_sessions,
            "active_sessions": len(self.active_sessions),
            "completed_sessions": self.completed_sessions,
            "failed_sessions": self.failed_sessions,
            "configured_menus": len(self.menus),
            "custom_handlers": len(self.custom_handlers),
            "success_rate": self.completed_sessions / max(self.total_sessions, 1)
        }
    
    def get_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get active IVR sessions."""
        current_time = time.time()
        
        return {
            call_id: {
                "session_id": session.session_id,
                "current_menu": session.current_menu_id,
                "duration_seconds": current_time - session.start_time,
                "retry_count": session.retry_count,
                "waiting_for_input": session.waiting_for_input,
                "menu_stack_depth": len(session.menu_stack)
            }
            for call_id, session in self.active_sessions.items()
        }
    
    def load_menus_from_config(self, config: Dict[str, Any]):
        """Load IVR menus from configuration."""
        try:
            for menu_config in config.get("menus", []):
                # Create menu
                menu = IVRMenu(
                    menu_id=menu_config["menu_id"],
                    name=menu_config["name"],
                    welcome_prompt=self._create_prompt_from_config(menu_config["welcome_prompt"]),
                    timeout_seconds=menu_config.get("timeout_seconds", 10.0),
                    max_retries=menu_config.get("max_retries", 3)
                )
                
                # Add optional prompts
                if "invalid_prompt" in menu_config:
                    menu.invalid_prompt = self._create_prompt_from_config(menu_config["invalid_prompt"])
                
                if "timeout_prompt" in menu_config:
                    menu.timeout_prompt = self._create_prompt_from_config(menu_config["timeout_prompt"])
                
                # Add menu items
                for item_config in menu_config.get("items", []):
                    action = IVRAction(
                        action_type=IVRActionType(item_config["action"]["type"]),
                        target=item_config["action"].get("target"),
                        parameters=item_config["action"].get("parameters", {})
                    )
                    
                    if "prompt" in item_config["action"]:
                        action.prompt = self._create_prompt_from_config(item_config["action"]["prompt"])
                    
                    item = IVRMenuItem(
                        digit=item_config["digit"],
                        description=item_config["description"],
                        action=action,
                        enabled=item_config.get("enabled", True)
                    )
                    
                    menu.add_item(item)
                
                self.add_menu(menu)
            
            # Set default menu
            if "default_menu" in config:
                self.default_menu_id = config["default_menu"]
            
            logger.info(f"Loaded {len(config.get('menus', []))} IVR menus from configuration")
            
        except Exception as e:
            logger.error(f"Error loading IVR menus: {e}")
            raise
    
    def _create_prompt_from_config(self, prompt_config: Dict[str, Any]) -> IVRPrompt:
        """Create IVR prompt from configuration."""
        return IVRPrompt(
            prompt_id=prompt_config.get("prompt_id", "unnamed"),
            prompt_type=IVRPromptType(prompt_config["type"]),
            content=prompt_config["content"],
            duration_seconds=prompt_config.get("duration_seconds"),
            volume=prompt_config.get("volume", 0.8),
            repeat_count=prompt_config.get("repeat_count", 1),
            interruptible=prompt_config.get("interruptible", True),
            tts_voice=prompt_config.get("tts_voice", "default"),
            tts_speed=prompt_config.get("tts_speed", 1.0),
            tone_frequency=prompt_config.get("tone_frequency"),
            tone_amplitude=prompt_config.get("tone_amplitude", 0.3)
        )
    
    async def start(self):
        """Start the IVR manager."""
        # Start the cleanup task
        if not hasattr(self, '_cleanup_task') or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        logger.info("IVR manager started")
    
    async def stop(self):
        """Stop the IVR manager."""
        # End all active sessions
        for call_id in list(self.active_sessions.keys()):
            await self.end_ivr_session(call_id, "stopping")
        
        # Cancel cleanup task
        if hasattr(self, '_cleanup_task'):
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("IVR manager stopped")
    
    async def cleanup(self):
        """Cleanup IVR manager resources."""
        try:
            # End all active sessions
            for call_id in list(self.active_sessions.keys()):
                await self.end_ivr_session(call_id, "cleanup")
            
            # Cancel cleanup task
            if hasattr(self, '_cleanup_task'):
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("IVR manager cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up IVR manager: {e}")
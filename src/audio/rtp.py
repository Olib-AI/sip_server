"""RTP packet handling for real-time audio processing."""
import struct
import socket
import asyncio
import time
from typing import Dict, Callable, Optional, Tuple
from dataclasses import dataclass
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


@dataclass
class RTPHeader:
    """RTP packet header structure."""
    version: int
    padding: bool
    extension: bool
    csrc_count: int
    marker: bool
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    
    @classmethod
    def parse(cls, data: bytes) -> 'RTPHeader':
        """Parse RTP header from packet data."""
        if len(data) < 12:
            raise ValueError("RTP packet too short")
        
        # Unpack fixed header (12 bytes)
        fields = struct.unpack('!BBHII', data[:12])
        
        # Parse first byte
        version = (fields[0] >> 6) & 0x3
        padding = bool((fields[0] >> 5) & 0x1)
        extension = bool((fields[0] >> 4) & 0x1)
        csrc_count = fields[0] & 0xF
        
        # Parse second byte
        marker = bool((fields[1] >> 7) & 0x1)
        payload_type = fields[1] & 0x7F
        
        return cls(
            version=version,
            padding=padding,
            extension=extension,
            csrc_count=csrc_count,
            marker=marker,
            payload_type=payload_type,
            sequence_number=fields[2],
            timestamp=fields[3],
            ssrc=fields[4]
        )
    
    def pack(self) -> bytes:
        """Pack RTP header into bytes."""
        # First byte: V(2) P(1) X(1) CC(4)
        byte1 = (self.version << 6) | (int(self.padding) << 5) | \
                (int(self.extension) << 4) | self.csrc_count
        
        # Second byte: M(1) PT(7)
        byte2 = (int(self.marker) << 7) | self.payload_type
        
        return struct.pack('!BBHII', byte1, byte2, self.sequence_number,
                          self.timestamp, self.ssrc)


@dataclass
class RTPPacket:
    """Complete RTP packet with header and payload."""
    header: RTPHeader
    payload: bytes
    
    @classmethod
    def parse(cls, data: bytes) -> 'RTPPacket':
        """Parse complete RTP packet."""
        header = RTPHeader.parse(data)
        
        # Calculate header size including CSRC list
        header_size = 12 + (header.csrc_count * 4)
        
        # Handle extension header if present
        if header.extension:
            if len(data) < header_size + 4:
                raise ValueError("RTP packet with extension too short")
            ext_length = struct.unpack('!H', data[header_size + 2:header_size + 4])[0]
            header_size += 4 + (ext_length * 4)
        
        # Extract payload
        payload = data[header_size:]
        
        # Handle padding if present
        if header.padding:
            if len(payload) > 0:
                padding_length = payload[-1]
                payload = payload[:-padding_length]
        
        return cls(header=header, payload=payload)
    
    def pack(self) -> bytes:
        """Pack complete RTP packet into bytes."""
        return self.header.pack() + self.payload


class RTPJitterBuffer:
    """Jitter buffer for RTP packet reordering and timing."""
    
    def __init__(self, max_size: int = 50, target_delay_ms: int = 60):
        self.max_size = max_size
        self.target_delay_ms = target_delay_ms
        self.packets: Dict[int, RTPPacket] = {}
        self.last_played_seq = None
        self.base_timestamp = None
        self.start_time = None
        
    def add_packet(self, packet: RTPPacket) -> None:
        """Add packet to jitter buffer."""
        seq_num = packet.header.sequence_number
        
        # Initialize base values with first packet
        if self.base_timestamp is None:
            self.base_timestamp = packet.header.timestamp
            self.start_time = time.time()
        
        # Drop duplicate packets
        if seq_num in self.packets:
            logger.debug(f"Dropping duplicate RTP packet {seq_num}")
            return
        
        # Add packet to buffer
        self.packets[seq_num] = packet
        
        # Limit buffer size
        if len(self.packets) > self.max_size:
            # Remove oldest packet
            oldest_seq = min(self.packets.keys())
            del self.packets[oldest_seq]
            logger.debug(f"Buffer full, dropped packet {oldest_seq}")
    
    def get_next_packet(self) -> Optional[RTPPacket]:
        """Get the next packet in sequence that's ready to play."""
        if not self.packets:
            return None
        
        # Determine next expected sequence number
        if self.last_played_seq is None:
            next_seq = min(self.packets.keys())
        else:
            next_seq = (self.last_played_seq + 1) & 0xFFFF  # Handle wraparound
        
        # Check if we have the next packet
        if next_seq in self.packets:
            packet = self.packets.pop(next_seq)
            self.last_played_seq = next_seq
            return packet
        
        # Check if we should skip and play the next available packet
        # (after waiting for target delay)
        if self.packets:
            current_time = time.time()
            elapsed_ms = (current_time - self.start_time) * 1000
            
            if elapsed_ms > self.target_delay_ms:
                # Play the earliest available packet
                earliest_seq = min(self.packets.keys())
                packet = self.packets.pop(earliest_seq)
                self.last_played_seq = earliest_seq
                logger.debug(f"Skipped to packet {earliest_seq} due to delay")
                return packet
        
        return None
    
    def clear(self) -> None:
        """Clear all packets from buffer."""
        self.packets.clear()
        self.last_played_seq = None
        self.base_timestamp = None
        self.start_time = None


class RTPSession:
    """RTP session handling for a single call."""
    
    def __init__(self, local_port: int, remote_host: str, remote_port: int,
                 payload_type: int = 0, codec: str = "PCMU"):
        self.local_port = local_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.payload_type = payload_type
        self.codec = codec
        
        self.socket: Optional[socket.socket] = None
        self.jitter_buffer = RTPJitterBuffer()
        self.sequence_number = 0
        self.timestamp = 0
        self.ssrc = int(time.time()) & 0xFFFFFFFF  # Random SSRC
        
        self.running = False
        self.receive_callback: Optional[Callable[[bytes], None]] = None
        
    async def start(self) -> None:
        """Start RTP session."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', self.local_port))
        self.socket.setblocking(False)
        self.running = True
        
        logger.info(f"RTP session started on port {self.local_port}")
        
        # Start receiving packets
        asyncio.create_task(self._receive_loop())
        asyncio.create_task(self._playout_loop())
    
    async def stop(self) -> None:
        """Stop RTP session."""
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None
        self.jitter_buffer.clear()
        logger.info(f"RTP session stopped on port {self.local_port}")
    
    def set_receive_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for received audio data."""
        self.receive_callback = callback
    
    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data via RTP."""
        if not self.socket or not self.running:
            return
        
        try:
            # Create RTP header
            header = RTPHeader(
                version=2,
                padding=False,
                extension=False,
                csrc_count=0,
                marker=False,
                payload_type=self.payload_type,
                sequence_number=self.sequence_number,
                timestamp=self.timestamp,
                ssrc=self.ssrc
            )
            
            # Create and send packet
            packet = RTPPacket(header=header, payload=audio_data)
            packet_data = packet.pack()
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.socket.sendto,
                packet_data,
                (self.remote_host, self.remote_port)
            )
            
            # Update sequence number and timestamp
            self.sequence_number = (self.sequence_number + 1) & 0xFFFF
            self.timestamp += len(audio_data)  # Adjust based on sample rate
            
        except Exception as e:
            logger.error(f"Error sending RTP packet: {e}")
    
    async def _receive_loop(self) -> None:
        """Main receive loop for RTP packets."""
        while self.running:
            try:
                data, addr = await asyncio.get_event_loop().run_in_executor(
                    None, self.socket.recvfrom, 1500
                )
                
                # Parse RTP packet
                packet = RTPPacket.parse(data)
                
                # Add to jitter buffer
                self.jitter_buffer.add_packet(packet)
                
            except socket.error:
                # Socket might be closed
                break
            except Exception as e:
                logger.error(f"Error receiving RTP packet: {e}")
                await asyncio.sleep(0.001)  # Small delay to prevent tight loop
    
    async def _playout_loop(self) -> None:
        """Playout loop for jitter buffer."""
        while self.running:
            try:
                packet = self.jitter_buffer.get_next_packet()
                if packet and self.receive_callback:
                    self.receive_callback(packet.payload)
                else:
                    await asyncio.sleep(0.020)  # 20ms frame interval
            except Exception as e:
                logger.error(f"Error in playout loop: {e}")
                await asyncio.sleep(0.020)


class RTPManager:
    """Manager for multiple RTP sessions."""
    
    def __init__(self, port_range: Tuple[int, int] = (10000, 20000)):
        self.port_range = port_range
        self.sessions: Dict[str, RTPSession] = {}
        self.used_ports = set()
    
    def allocate_port(self) -> int:
        """Allocate an available RTP port."""
        for port in range(self.port_range[0], self.port_range[1], 2):  # Even ports only
            if port not in self.used_ports:
                self.used_ports.add(port)
                return port
        raise RuntimeError("No available RTP ports")
    
    def release_port(self, port: int) -> None:
        """Release an RTP port."""
        self.used_ports.discard(port)
    
    async def create_session(self, call_id: str, remote_host: str, 
                           remote_port: int, codec: str = "PCMU") -> RTPSession:
        """Create a new RTP session for a call."""
        if call_id in self.sessions:
            await self.sessions[call_id].stop()
        
        local_port = self.allocate_port()
        
        # Map codec to payload type
        payload_type_map = {
            "PCMU": 0,
            "PCMA": 8,
            "G722": 9,
            "G729": 18
        }
        payload_type = payload_type_map.get(codec, 0)
        
        session = RTPSession(local_port, remote_host, remote_port, 
                           payload_type, codec)
        await session.start()
        
        self.sessions[call_id] = session
        logger.info(f"Created RTP session for call {call_id} on port {local_port}")
        
        return session
    
    async def destroy_session(self, call_id: str) -> None:
        """Destroy an RTP session."""
        if call_id in self.sessions:
            session = self.sessions[call_id]
            await session.stop()
            self.release_port(session.local_port)
            del self.sessions[call_id]
            logger.info(f"Destroyed RTP session for call {call_id}")
    
    def get_session(self, call_id: str) -> Optional[RTPSession]:
        """Get RTP session for a call."""
        return self.sessions.get(call_id)
    
    async def cleanup_all(self) -> None:
        """Clean up all RTP sessions."""
        for call_id in list(self.sessions.keys()):
            await self.destroy_session(call_id)


class RTPStatistics:
    """Statistics collection for RTP sessions."""
    
    def __init__(self):
        self.packets_sent = 0
        self.packets_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.packets_lost = 0
        self.jitter_ms = 0.0
        self.last_sequence = None
        self.sequence_gaps = deque(maxlen=100)
        self.packet_times = deque(maxlen=100)
    
    def record_sent_packet(self, packet_size: int) -> None:
        """Record a sent packet."""
        self.packets_sent += 1
        self.bytes_sent += packet_size
    
    def record_received_packet(self, packet: RTPPacket) -> None:
        """Record a received packet and update statistics."""
        self.packets_received += 1
        self.bytes_received += len(packet.payload)
        
        current_time = time.time()
        self.packet_times.append(current_time)
        
        # Track sequence numbers for loss detection
        seq_num = packet.header.sequence_number
        if self.last_sequence is not None:
            expected_seq = (self.last_sequence + 1) & 0xFFFF
            if seq_num != expected_seq:
                # Calculate how many packets were lost
                if seq_num > expected_seq:
                    lost = seq_num - expected_seq
                else:
                    # Handle wraparound
                    lost = (0xFFFF - expected_seq) + seq_num + 1
                
                self.packets_lost += lost
                self.sequence_gaps.append(lost)
        
        self.last_sequence = seq_num
        
        # Calculate jitter (simplified)
        if len(self.packet_times) >= 2:
            intervals = []
            for i in range(1, len(self.packet_times)):
                interval = self.packet_times[i] - self.packet_times[i-1]
                intervals.append(interval)
            
            if intervals:
                mean_interval = sum(intervals) / len(intervals)
                variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
                self.jitter_ms = (variance ** 0.5) * 1000  # Convert to ms
    
    def get_loss_rate(self) -> float:
        """Calculate packet loss rate."""
        total_expected = self.packets_received + self.packets_lost
        if total_expected == 0:
            return 0.0
        return self.packets_lost / total_expected
    
    def get_stats_dict(self) -> Dict:
        """Get statistics as dictionary."""
        return {
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'packets_lost': self.packets_lost,
            'loss_rate': self.get_loss_rate(),
            'jitter_ms': self.jitter_ms
        }
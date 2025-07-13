"""
SmartSync Protocol (SSP) - Client Implementation
Connects to SSP server and synchronizes files.
"""

import asyncio
import json
import logging
import time
import base64
from typing import Dict, List, Optional, Callable
from ssp_protocol import SSPProtocol, SSPMessage, MessageType, CHUNK_SIZE

logger = logging.getLogger(__name__)

class SSPClient:
    """SSP Client implementation"""
    
    def __init__(self, shared_secret: str, sync_folder: str, 
                 server_host: str = "localhost", server_port: int = 8888):
        self.protocol = SSPProtocol(shared_secret, sync_folder)
        self.server_host = server_host
        self.server_port = server_port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self.authenticated = False
        self.sync_in_progress = False
        self.sync_stats = {
            'files_received': 0,
            'bytes_received': 0,
            'files_sent': 0,
            'bytes_sent': 0,
            'sync_start_time': 0,
            'sync_duration': 0
        }
        self.pending_file_requests: Dict[str, Dict] = {}
        self.progress_callback: Optional[Callable] = None
        self.status_callback: Optional[Callable] = None
        self.running = False
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for sync progress updates"""
        self.progress_callback = callback
    
    def set_status_callback(self, callback: Callable):
        """Set callback for status updates"""
        self.status_callback = callback
    
    def _update_status(self, status: str, details: str = ""):
        """Update status and notify callback"""
        if self.status_callback:
            self.status_callback(status, details)
        logger.info(f"Status: {status} - {details}")
    
    def _update_progress(self, progress: Dict):
        """Update progress and notify callback"""
        if self.progress_callback:
            self.progress_callback(progress)
    
    async def connect(self) -> bool:
        """Connect to SSP server"""
        try:
            self._update_status("CONNECTING", f"Connecting to {self.server_host}:{self.server_port}")
            
            self.reader, self.writer = await asyncio.open_connection(
                self.server_host, self.server_port
            )
            
            self.connected = True
            self.running = True
            
            # Start message handling task
            asyncio.create_task(self._message_handler())
            
            # Start handshake
            await self._perform_handshake()
            
            self._update_status("CONNECTED", "Connected to server")
            return True
            
        except Exception as e:
            self._update_status("CONNECTION_ERROR", str(e))
            logger.error(f"Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from SSP server"""
        if self.writer:
            self.running = False
            self.writer.close()
            await self.writer.wait_closed()
            self.connected = False
            self.authenticated = False
            self._update_status("DISCONNECTED", "Disconnected from server")
    
    async def sync(self) -> bool:
        """Start file synchronization"""
        if not self.authenticated:
            self._update_status("SYNC_ERROR", "Not authenticated")
            return False
        
        try:
            self.sync_in_progress = True
            self.sync_stats['sync_start_time'] = time.time()
            
            self._update_status("SYNC_STARTED", "Starting synchronization")
            
            # Send our file index to server
            file_index_message = self.protocol.create_file_index_message()
            await self._send_message(file_index_message)
            
            # Wait for sync to complete
            while self.sync_in_progress and self.running:
                await asyncio.sleep(0.1)
            
            self.sync_stats['sync_duration'] = time.time() - self.sync_stats['sync_start_time']
            
            self._update_status("SYNC_COMPLETED", 
                               f"Sync completed in {self.sync_stats['sync_duration']:.2f}s")
            
            return True
            
        except Exception as e:
            self._update_status("SYNC_ERROR", str(e))
            logger.error(f"Sync error: {e}")
            return False
    
    async def _perform_handshake(self):
        """Perform initial handshake with server"""
        try:
            # Send HELLO message
            hello_message = self.protocol.create_hello_message()
            await self._send_message(hello_message)
            
            self._update_status("HANDSHAKE", "Handshake initiated")
            
        except Exception as e:
            logger.error(f"Handshake error: {e}")
            raise
    
    async def _message_handler(self):
        """Handle incoming messages from server"""
        buffer = b""
        
        while self.running and self.connected:
            try:
                # Read data with timeout
                data = await asyncio.wait_for(self.reader.read(4096), timeout=30.0)
                if not data:
                    break
                
                buffer += data
                
                # Process complete messages
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line.strip():
                        await self._process_message(line.decode('utf-8'))
                
            except asyncio.TimeoutError:
                # Send heartbeat if no activity
                await self._send_heartbeat()
            except Exception as e:
                logger.error(f"Message handler error: {e}")
                break
    
    async def _process_message(self, message_data: str):
        """Process incoming message from server"""
        try:
            message = self.protocol.deserialize_message(message_data)
            if not message:
                logger.error("Failed to deserialize message")
                return
            
            logger.info(f"Received {message.type} from server")
            
            # Handle different message types
            if message.type == MessageType.AUTH:
                await self._handle_auth(message)
            elif message.type == MessageType.FILE_INDEX:
                await self._handle_file_index(message)
            elif message.type == MessageType.FILE_CHUNK:
                await self._handle_file_chunk(message)
            elif message.type == MessageType.ACK:
                await self._handle_ack(message)
            elif message.type == MessageType.SYNC_COMPLETE:
                await self._handle_sync_complete(message)
            elif message.type == MessageType.ERROR:
                await self._handle_error(message)
            elif message.type == MessageType.HEARTBEAT:
                await self._handle_heartbeat(message)
            else:
                logger.warning(f"Unknown message type: {message.type}")
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_auth(self, message: SSPMessage):
        """Handle AUTH message (challenge from server)"""
        try:
            challenge = message.payload.get('auth_challenge')
            if not challenge:
                logger.error("No auth challenge received")
                return
            
            # Respond to challenge
            auth_response = self.protocol.create_auth_message(challenge)
            await self._send_message(auth_response)
            
            self._update_status("AUTH_CHALLENGE", "Responding to authentication challenge")
            
        except Exception as e:
            logger.error(f"Auth error: {e}")
    
    async def _handle_file_index(self, message: SSPMessage):
        """Handle FILE_INDEX message from server"""
        try:
            remote_files = message.payload.get('files', {})
            missing_files = self.protocol.get_missing_files(remote_files)
            
            logger.info(f"Need to request {len(missing_files)} files")
            
            # Send ACK for file index
            ack_message = self.protocol.create_ack_message("FILE_INDEX", message.sequence_id)
            await self._send_message(ack_message)
            
            # Request missing files
            for file_path in missing_files:
                file_request = self.protocol.create_file_request_message(file_path)
                await self._send_message(file_request)
                
                # Track pending request
                self.pending_file_requests[file_request.payload['request_id']] = {
                    'file_path': file_path,
                    'request_time': time.time()
                }
            
            if not missing_files:
                # No files to sync, send completion
                await self._send_sync_complete()
            
            self._update_progress({
                'phase': 'requesting',
                'files_to_request': len(missing_files),
                'files_received': 0
            })
            
        except Exception as e:
            logger.error(f"File index error: {e}")
    
    async def _handle_file_chunk(self, message: SSPMessage):
        """Handle FILE_CHUNK message from server"""
        try:
            file_path = message.payload.get('file_path')
            chunk_index = message.payload.get('chunk_index')
            total_chunks = message.payload.get('total_chunks')
            chunk_data_b64 = message.payload.get('chunk_data')
            request_id = message.payload.get('request_id')
            
            if not all([file_path, chunk_data_b64, request_id is not None]):
                logger.error("Invalid file chunk message")
                return
            
            # Decode chunk data
            chunk_data = base64.b64decode(chunk_data_b64)
            
            # Save chunk
            file_complete = self.protocol.save_file_chunk(
                file_path, chunk_index, chunk_data, total_chunks, request_id
            )
            
            # Send ACK for chunk
            ack_message = self.protocol.create_ack_message("FILE_CHUNK", message.sequence_id)
            await self._send_message(ack_message)
            
            # Update progress
            progress = {
                'phase': 'receiving',
                'file_path': file_path,
                'chunk_index': chunk_index,
                'total_chunks': total_chunks,
                'progress': (chunk_index + 1) / total_chunks * 100
            }
            self._update_progress(progress)
            
            if file_complete:
                logger.info(f"Completed receiving file: {file_path}")
                self.sync_stats['files_received'] += 1
                self.sync_stats['bytes_received'] += len(chunk_data)
                
                # Remove from pending requests
                if request_id in self.pending_file_requests:
                    del self.pending_file_requests[request_id]
                
                # Check if all files received
                if not self.pending_file_requests:
                    await self._send_sync_complete()
            
        except Exception as e:
            logger.error(f"File chunk error: {e}")
    
    async def _handle_ack(self, message: SSPMessage):
        """Handle ACK message from server"""
        try:
            ack_type = message.payload.get('ack_type')
            
            if ack_type == "AUTH":
                self.authenticated = True
                self._update_status("AUTHENTICATED", "Authentication successful")
            elif ack_type == "HEARTBEAT":
                # Heartbeat acknowledged
                pass
            else:
                logger.info(f"Received ACK for {ack_type}")
            
        except Exception as e:
            logger.error(f"ACK error: {e}")
    
    async def _handle_sync_complete(self, message: SSPMessage):
        """Handle SYNC_COMPLETE message from server"""
        try:
            self.sync_in_progress = False
            
            server_stats = message.payload.get('sync_stats', {})
            completion_time = message.payload.get('completion_time')
            
            logger.info(f"Sync completed. Server stats: {server_stats}")
            
            self._update_status("SYNC_COMPLETE", "Synchronization completed successfully")
            
        except Exception as e:
            logger.error(f"Sync complete error: {e}")
    
    async def _handle_error(self, message: SSPMessage):
        """Handle ERROR message from server"""
        try:
            error_code = message.payload.get('error_code')
            error_message = message.payload.get('error_message')
            
            logger.error(f"Server error [{error_code}]: {error_message}")
            self._update_status("SERVER_ERROR", f"{error_code}: {error_message}")
            
        except Exception as e:
            logger.error(f"Error handling error: {e}")
    
    async def _handle_heartbeat(self, message: SSPMessage):
        """Handle HEARTBEAT message from server"""
        try:
            # Respond with heartbeat ACK
            ack_message = self.protocol.create_ack_message("HEARTBEAT", message.sequence_id)
            await self._send_message(ack_message)
            
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
    
    async def _send_message(self, message: SSPMessage):
        """Send message to server"""
        if not self.writer:
            raise Exception("Not connected to server")
        
        try:
            serialized = self.protocol.serialize_message(message)
            self.writer.write(serialized.encode('utf-8') + b'\n')
            await self.writer.drain()
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
    
    async def _send_heartbeat(self):
        """Send heartbeat to server"""
        try:
            heartbeat_message = self.protocol.create_message(MessageType.HEARTBEAT, {
                'timestamp': time.time(),
                'client_status': 'active'
            })
            await self._send_message(heartbeat_message)
        except Exception as e:
            logger.error(f"Heartbeat send error: {e}")
    
    async def _send_sync_complete(self):
        """Send sync complete notification to server"""
        try:
            ack_message = self.protocol.create_ack_message("SYNC_COMPLETE")
            await self._send_message(ack_message)
            
            logger.info("Sent sync complete to server")
            
        except Exception as e:
            logger.error(f"Sync complete send error: {e}")
    
    def get_sync_stats(self) -> Dict:
        """Get current synchronization statistics"""
        return self.sync_stats.copy()
    
    def get_client_status(self) -> Dict:
        """Get current client status"""
        return {
            'connected': self.connected,
            'authenticated': self.authenticated,
            'sync_in_progress': self.sync_in_progress,
            'server_host': self.server_host,
            'server_port': self.server_port,
            'sync_folder': str(self.protocol.sync_folder),
            'stats': self.sync_stats.copy(),
            'pending_requests': len(self.pending_file_requests)
        }

# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python ssp_client.py <shared_secret> <sync_folder> [server_host] [server_port]")
        sys.exit(1)
    
    shared_secret = sys.argv[1]
    sync_folder = sys.argv[2]
    server_host = sys.argv[3] if len(sys.argv) > 3 else "localhost"
    server_port = int(sys.argv[4]) if len(sys.argv) > 4 else 8888
    
    client = SSPClient(shared_secret, sync_folder, server_host, server_port)
    
    # Set up logging callbacks
    def status_callback(status, details):
        print(f"Status: {status} - {details}")
    
    def progress_callback(progress):
        if progress.get('phase') == 'receiving':
            print(f"Receiving {progress['file_path']}: {progress['progress']:.1f}%")
    
    client.set_status_callback(status_callback)
    client.set_progress_callback(progress_callback)
    
    async def main():
        try:
            if await client.connect():
                await client.sync()
                await asyncio.sleep(1)  # Give time for final messages
                await client.disconnect()
            else:
                print("Failed to connect to server")
        except KeyboardInterrupt:
            print("Client stopped by user")
            await client.disconnect()
        except Exception as e:
            print(f"Client error: {e}")
    
    asyncio.run(main())

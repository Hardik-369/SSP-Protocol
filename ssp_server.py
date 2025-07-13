"""
SmartSync Protocol (SSP) - Server Implementation
Handles incoming client connections and file synchronization requests.
"""

import asyncio
import json
import logging
import time
import base64
from typing import Dict, List, Optional, Set
from ssp_protocol import SSPProtocol, SSPMessage, MessageType, CHUNK_SIZE

logger = logging.getLogger(__name__)

class SSPServer:
    """SSP Server implementation"""
    
    def __init__(self, shared_secret: str, sync_folder: str, 
                 host: str = "localhost", port: int = 8888):
        self.protocol = SSPProtocol(shared_secret, sync_folder)
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.connected_clients: Dict[str, asyncio.StreamWriter] = {}
        self.client_states: Dict[str, Dict] = {}
        self.running = False
        self.sync_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'files_sent': 0,
            'bytes_sent': 0,
            'sync_sessions': 0
        }
    
    async def start(self):
        """Start the SSP server"""
        try:
            # Check if server is already running
            if self.server is not None and not self.server.is_closing():
                logger.info(f"Server already running on {self.host}:{self.port}")
                return
            
            self.server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )
            self.running = True
            logger.info(f"SSP Server started on {self.host}:{self.port}")
            
            # Start heartbeat task
            asyncio.create_task(self._heartbeat_task())
            
            async with self.server:
                await self.server.serve_forever()
        except OSError as e:
            if e.errno == 10048:  # Windows error code for "address already in use"
                logger.error(f"Port {self.port} is already in use. Please choose a different port.")
            else:
                logger.error(f"Error starting server: {e}")
            raise
        except Exception as e:
            logger.error(f"Error starting server: {e}")
            raise
    
    async def stop(self):
        """Stop the SSP server"""
        if self.server:
            self.running = False
            self.server.close()
            await self.server.wait_closed()
            
            # Close all client connections
            for client_id, writer in self.connected_clients.items():
                writer.close()
                await writer.wait_closed()
            
            self.connected_clients.clear()
            self.client_states.clear()
            logger.info("SSP Server stopped")
    
    async def _handle_client(self, reader: asyncio.StreamReader, 
                           writer: asyncio.StreamWriter):
        """Handle incoming client connection"""
        client_addr = writer.get_extra_info('peername')
        client_id = f"{client_addr[0]}:{client_addr[1]}"
        
        logger.info(f"New client connected: {client_id}")
        
        # Initialize client state
        self.connected_clients[client_id] = writer
        self.client_states[client_id] = {
            'authenticated': False,
            'handshake_complete': False,
            'sync_in_progress': False,
            'last_heartbeat': time.time(),
            'pending_requests': {},
            'file_index_sent': False
        }
        
        self.sync_stats['total_connections'] += 1
        self.sync_stats['active_connections'] += 1
        
        try:
            await self._client_session(reader, writer, client_id)
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            # Clean up client connection
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
            if client_id in self.client_states:
                del self.client_states[client_id]
            
            self.sync_stats['active_connections'] -= 1
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client {client_id} disconnected")
    
    async def _client_session(self, reader: asyncio.StreamReader, 
                            writer: asyncio.StreamWriter, client_id: str):
        """Handle client session messages"""
        buffer = b""
        
        while self.running:
            try:
                # Read data with timeout
                data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                if not data:
                    break
                
                buffer += data
                
                # Process complete messages
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line.strip():
                        await self._process_message(line.decode('utf-8'), writer, client_id)
                
            except asyncio.TimeoutError:
                # Send heartbeat if no activity
                await self._send_heartbeat(writer, client_id)
            except Exception as e:
                logger.error(f"Error in client session {client_id}: {e}")
                break
    
    async def _process_message(self, message_data: str, 
                             writer: asyncio.StreamWriter, client_id: str):
        """Process incoming message from client"""
        try:
            message = self.protocol.deserialize_message(message_data)
            if not message:
                await self._send_error(writer, "INVALID_MESSAGE", "Failed to deserialize message")
                return
            
            client_state = self.client_states[client_id]
            client_state['last_heartbeat'] = time.time()
            
            logger.info(f"Received {message.type} from {client_id}")
            
            # Handle different message types
            if message.type == MessageType.HELLO:
                await self._handle_hello(message, writer, client_id)
            elif message.type == MessageType.AUTH:
                await self._handle_auth(message, writer, client_id)
            elif message.type == MessageType.FILE_INDEX:
                await self._handle_file_index(message, writer, client_id)
            elif message.type == MessageType.FILE_REQUEST:
                await self._handle_file_request(message, writer, client_id)
            elif message.type == MessageType.ACK:
                await self._handle_ack(message, writer, client_id)
            elif message.type == MessageType.HEARTBEAT:
                await self._handle_heartbeat(message, writer, client_id)
            else:
                await self._send_error(writer, "UNKNOWN_MESSAGE", f"Unknown message type: {message.type}")
        
        except Exception as e:
            logger.error(f"Error processing message from {client_id}: {e}")
            await self._send_error(writer, "PROCESSING_ERROR", str(e))
    
    async def _handle_hello(self, message: SSPMessage, 
                          writer: asyncio.StreamWriter, client_id: str):
        """Handle HELLO message"""
        client_state = self.client_states[client_id]
        
        # Validate version
        if message.payload.get('version') != '1.0':
            await self._send_error(writer, "VERSION_MISMATCH", "Unsupported protocol version")
            return
        
        # Send auth challenge
        auth_message = self.protocol.create_auth_message()
        await self._send_message(writer, auth_message)
        
        # Store challenge for verification
        client_state['auth_challenge'] = auth_message.payload['auth_challenge']
        client_state['handshake_complete'] = True
    
    async def _handle_auth(self, message: SSPMessage, 
                         writer: asyncio.StreamWriter, client_id: str):
        """Handle AUTH message"""
        client_state = self.client_states[client_id]
        
        if 'auth_challenge' not in client_state:
            await self._send_error(writer, "AUTH_ERROR", "No challenge sent")
            return
        
        # Verify auth response
        challenge = client_state['auth_challenge']
        expected_response = self.protocol._generate_hmac(challenge)
        received_response = message.payload.get('auth_response')
        
        if expected_response == received_response:
            client_state['authenticated'] = True
            ack_message = self.protocol.create_ack_message("AUTH", message.sequence_id)
            await self._send_message(writer, ack_message)
            
            # Send our file index after successful auth
            file_index_message = self.protocol.create_file_index_message()
            await self._send_message(writer, file_index_message)
            client_state['file_index_sent'] = True
            
            logger.info(f"Client {client_id} authenticated successfully")
        else:
            await self._send_error(writer, "AUTH_FAILED", "Authentication failed")
    
    async def _handle_file_index(self, message: SSPMessage, 
                               writer: asyncio.StreamWriter, client_id: str):
        """Handle FILE_INDEX message"""
        client_state = self.client_states[client_id]
        
        if not client_state['authenticated']:
            await self._send_error(writer, "NOT_AUTHENTICATED", "Authentication required")
            return
        
        # Compare file indexes and determine what to send
        remote_files = message.payload.get('files', {})
        missing_files = self.protocol.get_missing_files(remote_files)
        
        logger.info(f"Client {client_id} needs {len(missing_files)} files")
        
        # Send ACK for file index
        ack_message = self.protocol.create_ack_message("FILE_INDEX", message.sequence_id)
        await self._send_message(writer, ack_message)
        
        # Start sync session
        client_state['sync_in_progress'] = True
        client_state['files_to_send'] = missing_files
        client_state['sync_start_time'] = time.time()
        
        self.sync_stats['sync_sessions'] += 1
    
    async def _handle_file_request(self, message: SSPMessage, 
                                 writer: asyncio.StreamWriter, client_id: str):
        """Handle FILE_REQUEST message"""
        client_state = self.client_states[client_id]
        
        if not client_state['authenticated']:
            await self._send_error(writer, "NOT_AUTHENTICATED", "Authentication required")
            return
        
        file_path = message.payload.get('file_path')
        request_id = message.payload.get('request_id')
        
        if not file_path:
            await self._send_error(writer, "INVALID_REQUEST", "Missing file_path")
            return
        
        # Send file in chunks
        await self._send_file_chunks(writer, file_path, request_id, client_id)
    
    async def _send_file_chunks(self, writer: asyncio.StreamWriter, 
                              file_path: str, request_id: str, client_id: str):
        """Send file in chunks to client"""
        try:
            chunks = self.protocol.read_file_chunks(file_path)
            if not chunks:
                await self._send_error(writer, "FILE_NOT_FOUND", f"Cannot read file: {file_path}")
                return
            
            total_chunks = len(chunks)
            logger.info(f"Sending {file_path} in {total_chunks} chunks to {client_id}")
            
            # Send all chunks
            for i, chunk_data in enumerate(chunks):
                chunk_message = self.protocol.create_file_chunk_message(
                    file_path, i, chunk_data, total_chunks, request_id
                )
                await self._send_message(writer, chunk_message)
                
                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.01)
            
            # Update stats
            self.sync_stats['files_sent'] += 1
            self.sync_stats['bytes_sent'] += sum(len(chunk) for chunk in chunks)
            
            logger.info(f"Completed sending {file_path} to {client_id}")
            
        except Exception as e:
            logger.error(f"Error sending file {file_path} to {client_id}: {e}")
            await self._send_error(writer, "SEND_ERROR", str(e))
    
    async def _handle_ack(self, message: SSPMessage, 
                        writer: asyncio.StreamWriter, client_id: str):
        """Handle ACK message"""
        client_state = self.client_states[client_id]
        ack_type = message.payload.get('ack_type')
        
        if ack_type == "SYNC_COMPLETE":
            # Client completed sync
            client_state['sync_in_progress'] = False
            sync_duration = time.time() - client_state.get('sync_start_time', time.time())
            
            # Send sync complete confirmation
            stats = {
                'files_sent': self.sync_stats['files_sent'],
                'bytes_sent': self.sync_stats['bytes_sent'],
                'sync_duration': sync_duration
            }
            
            sync_complete_message = self.protocol.create_sync_complete_message(stats)
            await self._send_message(writer, sync_complete_message)
            
            logger.info(f"Sync completed with {client_id} in {sync_duration:.2f}s")
    
    async def _handle_heartbeat(self, message: SSPMessage, 
                             writer: asyncio.StreamWriter, client_id: str):
        """Handle HEARTBEAT message"""
        # Respond with heartbeat ACK
        ack_message = self.protocol.create_ack_message("HEARTBEAT", message.sequence_id)
        await self._send_message(writer, ack_message)
    
    async def _send_message(self, writer: asyncio.StreamWriter, message: SSPMessage):
        """Send message to client"""
        try:
            serialized = self.protocol.serialize_message(message)
            writer.write(serialized.encode('utf-8') + b'\n')
            await writer.drain()
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def _send_error(self, writer: asyncio.StreamWriter, 
                        error_code: str, error_message: str):
        """Send error message to client"""
        error_msg = self.protocol.create_error_message(error_code, error_message)
        await self._send_message(writer, error_msg)
    
    async def _send_heartbeat(self, writer: asyncio.StreamWriter, client_id: str):
        """Send heartbeat to client"""
        heartbeat_message = self.protocol.create_message(MessageType.HEARTBEAT, {
            'timestamp': time.time(),
            'server_status': 'active'
        })
        await self._send_message(writer, heartbeat_message)
    
    async def _heartbeat_task(self):
        """Background task to monitor client connections"""
        while self.running:
            try:
                current_time = time.time()
                disconnected_clients = []
                
                for client_id, client_state in self.client_states.items():
                    last_heartbeat = client_state.get('last_heartbeat', current_time)
                    
                    # Check for timeout
                    if current_time - last_heartbeat > 60:  # 1 minute timeout
                        disconnected_clients.append(client_id)
                
                # Clean up disconnected clients
                for client_id in disconnected_clients:
                    logger.info(f"Client {client_id} timed out")
                    if client_id in self.connected_clients:
                        writer = self.connected_clients[client_id]
                        writer.close()
                        await writer.wait_closed()
                        del self.connected_clients[client_id]
                    
                    if client_id in self.client_states:
                        del self.client_states[client_id]
                    
                    self.sync_stats['active_connections'] -= 1
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                await asyncio.sleep(30)
    
    def get_server_status(self) -> Dict:
        """Get current server status"""
        return {
            'running': self.running,
            'host': self.host,
            'port': self.port,
            'active_connections': len(self.connected_clients),
            'sync_folder': str(self.protocol.sync_folder),
            'stats': self.sync_stats.copy(),
            'clients': list(self.client_states.keys())
        }

# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python ssp_server.py <shared_secret> <sync_folder> [host] [port]")
        sys.exit(1)
    
    shared_secret = sys.argv[1]
    sync_folder = sys.argv[2]
    host = sys.argv[3] if len(sys.argv) > 3 else "localhost"
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 8888
    
    server = SSPServer(shared_secret, sync_folder, host, port)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("Server stopped by user")
    except Exception as e:
        print(f"Server error: {e}")

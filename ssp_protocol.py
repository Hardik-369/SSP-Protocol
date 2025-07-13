"""
SmartSync Protocol (SSP) - Core Protocol Implementation
A lightweight, secure, and efficient peer-to-peer file synchronization protocol.
"""

import asyncio
import json
import base64
import hashlib
import hmac
import os
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Protocol constants
PROTOCOL_VERSION = "1.0"
CHUNK_SIZE = 4096  # 4KB chunks
MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB max message size
HEARTBEAT_INTERVAL = 30  # seconds
SYNC_TIMEOUT = 300  # 5 minutes

# Message types
class MessageType:
    HELLO = "HELLO"
    AUTH = "AUTH"
    FILE_INDEX = "FILE_INDEX"
    FILE_REQUEST = "FILE_REQUEST"
    FILE_CHUNK = "FILE_CHUNK"
    ACK = "ACK"
    SYNC_COMPLETE = "SYNC_COMPLETE"
    ERROR = "ERROR"
    HEARTBEAT = "HEARTBEAT"

@dataclass
class FileInfo:
    """File information structure"""
    path: str
    size: int
    hash: str
    modified_time: float

@dataclass
class SSPMessage:
    """SSP protocol message structure"""
    type: str
    payload: Dict[str, Any]
    timestamp: float
    sequence_id: Optional[int] = None

class SSPProtocol:
    """SmartSync Protocol implementation"""
    
    def __init__(self, shared_secret: str, sync_folder: str):
        self.shared_secret = shared_secret.encode('utf-8')
        self.sync_folder = Path(sync_folder)
        self.sync_folder.mkdir(parents=True, exist_ok=True)
        self.file_index: Dict[str, FileInfo] = {}
        self.sequence_counter = 0
        self.authenticated_peers: Dict[str, bool] = {}
        self.active_transfers: Dict[str, Dict] = {}
        
    def _generate_hmac(self, message: str) -> str:
        """Generate HMAC for message authentication"""
        return hmac.new(
            self.shared_secret,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _verify_hmac(self, message: str, received_hmac: str) -> bool:
        """Verify HMAC for message authentication"""
        expected_hmac = self._generate_hmac(message)
        return hmac.compare_digest(expected_hmac, received_hmac)
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        hasher = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(CHUNK_SIZE):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return ""
    
    def _scan_folder(self) -> Dict[str, FileInfo]:
        """Scan sync folder and build file index"""
        file_index = {}
        
        for file_path in self.sync_folder.rglob('*'):
            if file_path.is_file():
                try:
                    relative_path = file_path.relative_to(self.sync_folder)
                    stat = file_path.stat()
                    
                    file_info = FileInfo(
                        path=str(relative_path),
                        size=stat.st_size,
                        hash=self._calculate_file_hash(file_path),
                        modified_time=stat.st_mtime
                    )
                    file_index[str(relative_path)] = file_info
                except Exception as e:
                    logger.error(f"Error scanning file {file_path}: {e}")
        
        return file_index
    
    def create_message(self, msg_type: str, payload: Dict[str, Any]) -> SSPMessage:
        """Create an SSP message"""
        self.sequence_counter += 1
        return SSPMessage(
            type=msg_type,
            payload=payload,
            timestamp=time.time(),
            sequence_id=self.sequence_counter
        )
    
    def serialize_message(self, message: SSPMessage) -> str:
        """Serialize message to JSON string with authentication"""
        message_dict = asdict(message)
        message_json = json.dumps(message_dict, separators=(',', ':'))
        
        # Add HMAC for authentication
        auth_message = {
            'message': message_json,
            'hmac': self._generate_hmac(message_json)
        }
        
        return json.dumps(auth_message)
    
    def deserialize_message(self, data: str) -> Optional[SSPMessage]:
        """Deserialize and verify message"""
        try:
            auth_message = json.loads(data)
            message_json = auth_message['message']
            received_hmac = auth_message['hmac']
            
            # Verify HMAC
            if not self._verify_hmac(message_json, received_hmac):
                logger.error("HMAC verification failed")
                return None
            
            message_dict = json.loads(message_json)
            return SSPMessage(**message_dict)
        
        except Exception as e:
            logger.error(f"Error deserializing message: {e}")
            return None
    
    def create_hello_message(self) -> SSPMessage:
        """Create HELLO message for handshake"""
        payload = {
            'version': PROTOCOL_VERSION,
            'capabilities': ['chunked_transfer', 'hmac_auth'],
            'client_id': hashlib.sha256(self.shared_secret).hexdigest()[:16]
        }
        return self.create_message(MessageType.HELLO, payload)
    
    def create_auth_message(self, challenge: str = None) -> SSPMessage:
        """Create AUTH message"""
        if challenge:
            # Respond to challenge
            response = self._generate_hmac(challenge)
            payload = {'auth_response': response}
        else:
            # Send challenge
            challenge = base64.b64encode(os.urandom(32)).decode('utf-8')
            payload = {'auth_challenge': challenge}
        
        return self.create_message(MessageType.AUTH, payload)
    
    def create_file_index_message(self) -> SSPMessage:
        """Create FILE_INDEX message"""
        self.file_index = self._scan_folder()
        
        # Convert FileInfo objects to dictionaries
        file_index_dict = {}
        for path, file_info in self.file_index.items():
            file_index_dict[path] = asdict(file_info)
        
        payload = {
            'file_count': len(self.file_index),
            'files': file_index_dict
        }
        
        return self.create_message(MessageType.FILE_INDEX, payload)
    
    def create_file_request_message(self, file_path: str) -> SSPMessage:
        """Create FILE_REQUEST message"""
        payload = {
            'file_path': file_path,
            'request_id': f"req_{self.sequence_counter}"
        }
        return self.create_message(MessageType.FILE_REQUEST, payload)
    
    def create_file_chunk_message(self, file_path: str, chunk_index: int, 
                                 chunk_data: bytes, total_chunks: int,
                                 request_id: str) -> SSPMessage:
        """Create FILE_CHUNK message"""
        payload = {
            'file_path': file_path,
            'chunk_index': chunk_index,
            'total_chunks': total_chunks,
            'chunk_data': base64.b64encode(chunk_data).decode('utf-8'),
            'chunk_size': len(chunk_data),
            'request_id': request_id
        }
        return self.create_message(MessageType.FILE_CHUNK, payload)
    
    def create_ack_message(self, ack_type: str, reference_id: str = None) -> SSPMessage:
        """Create ACK message"""
        payload = {
            'ack_type': ack_type,
            'reference_id': reference_id,
            'status': 'success'
        }
        return self.create_message(MessageType.ACK, payload)
    
    def create_sync_complete_message(self, stats: Dict[str, Any]) -> SSPMessage:
        """Create SYNC_COMPLETE message"""
        payload = {
            'sync_stats': stats,
            'completion_time': time.time()
        }
        return self.create_message(MessageType.SYNC_COMPLETE, payload)
    
    def create_error_message(self, error_code: str, error_message: str) -> SSPMessage:
        """Create ERROR message"""
        payload = {
            'error_code': error_code,
            'error_message': error_message
        }
        return self.create_message(MessageType.ERROR, payload)
    
    def get_missing_files(self, remote_file_index: Dict[str, Dict]) -> List[str]:
        """Compare file indexes and return missing files"""
        local_files = set(self.file_index.keys())
        remote_files = set(remote_file_index.keys())
        
        missing_files = []
        
        # Files that exist remotely but not locally
        for file_path in remote_files - local_files:
            missing_files.append(file_path)
        
        # Files that exist locally but are outdated
        for file_path in local_files & remote_files:
            local_file = self.file_index[file_path]
            remote_file = remote_file_index[file_path]
            
            if (local_file.hash != remote_file['hash'] or 
                local_file.modified_time < remote_file['modified_time']):
                missing_files.append(file_path)
        
        return missing_files
    
    def save_file_chunk(self, file_path: str, chunk_index: int, 
                       chunk_data: bytes, total_chunks: int,
                       request_id: str) -> bool:
        """Save received file chunk"""
        try:
            full_path = self.sync_folder / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize transfer tracking
            if request_id not in self.active_transfers:
                self.active_transfers[request_id] = {
                    'file_path': file_path,
                    'total_chunks': total_chunks,
                    'received_chunks': {},
                    'temp_file': full_path.with_suffix('.tmp')
                }
            
            transfer = self.active_transfers[request_id]
            transfer['received_chunks'][chunk_index] = chunk_data
            
            # Check if all chunks received
            if len(transfer['received_chunks']) == total_chunks:
                # Write complete file
                with open(transfer['temp_file'], 'wb') as f:
                    for i in range(total_chunks):
                        f.write(transfer['received_chunks'][i])
                
                # Move temp file to final location
                transfer['temp_file'].replace(full_path)
                
                # Update file index
                self.file_index[file_path] = FileInfo(
                    path=file_path,
                    size=full_path.stat().st_size,
                    hash=self._calculate_file_hash(full_path),
                    modified_time=full_path.stat().st_mtime
                )
                
                # Clean up
                del self.active_transfers[request_id]
                return True
            
            return False  # Transfer not complete yet
            
        except Exception as e:
            logger.error(f"Error saving file chunk: {e}")
            return False
    
    def read_file_chunks(self, file_path: str) -> List[bytes]:
        """Read file and return chunks"""
        chunks = []
        full_path = self.sync_folder / file_path
        
        try:
            with open(full_path, 'rb') as f:
                while chunk := f.read(CHUNK_SIZE):
                    chunks.append(chunk)
            return chunks
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return []

"""
SmartSync Protocol (SSP) - Streamlit User Interface
Web interface for managing SSP server and client operations.
"""

import streamlit as st
import asyncio
import threading
import time
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import queue
import logging

# Import SSP modules
from ssp_server import SSPServer
from ssp_client import SSPClient
from ssp_protocol import SSPProtocol

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_session_state():
    """Initialize session state variables"""
    if 'server_instance' not in st.session_state:
        st.session_state.server_instance = None
    if 'client_instance' not in st.session_state:
        st.session_state.client_instance = None
    if 'server_logs' not in st.session_state:
        st.session_state.server_logs = []
    if 'client_logs' not in st.session_state:
        st.session_state.client_logs = []
    if 'sync_progress' not in st.session_state:
        st.session_state.sync_progress = {}
    if 'client_status' not in st.session_state:
        st.session_state.client_status = "DISCONNECTED"
    if 'server_status' not in st.session_state:
        st.session_state.server_status = "STOPPED"

# Initialize session state
initialize_session_state()

class StreamlitLogHandler(logging.Handler):
    """Custom log handler that stores logs in session state"""
    
    def __init__(self, log_list: List[str]):
        super().__init__()
        self.log_list = log_list
    
    def emit(self, record):
        log_entry = self.format(record)
        self.log_list.append(f"{time.strftime('%H:%M:%S')} - {log_entry}")
        # Keep only last 100 logs
        if len(self.log_list) > 100:
            self.log_list.pop(0)

def add_log_handler(log_list: List[str]):
    """Add custom log handler to capture logs"""
    handler = StreamlitLogHandler(log_list)
    handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(handler)

def run_server_thread(server: SSPServer):
    """Run server in a separate thread"""
    try:
        asyncio.run(server.start())
    except Exception as e:
        logger.error(f"Server error: {e}")
        st.session_state.server_status = "ERROR"

def run_client_sync_thread(client: SSPClient):
    """Run client sync in a separate thread"""
    async def client_sync():
        try:
            if await client.connect():
                await client.sync()
                await asyncio.sleep(1)  # Give time for final messages
                await client.disconnect()
            else:
                logger.error("Failed to connect to server")
        except Exception as e:
            logger.error(f"Client error: {e}")
    
    try:
        asyncio.run(client_sync())
    except Exception as e:
        logger.error(f"Client sync error: {e}")

def status_callback(status: str, details: str):
    """Callback for client status updates"""
    try:
        st.session_state.client_status = status
        if 'client_logs' not in st.session_state:
            st.session_state.client_logs = []
        st.session_state.client_logs.append(f"{time.strftime('%H:%M:%S')} - {status}: {details}")
        if len(st.session_state.client_logs) > 100:
            st.session_state.client_logs.pop(0)
    except Exception as e:
        logger.error(f"Client status callback error: {e}")

def progress_callback(progress: Dict):
    """Callback for sync progress updates"""
    try:
        st.session_state.sync_progress = progress
    except Exception as e:
        logger.error(f"Progress callback error: {e}")

def main():
    """Main Streamlit application"""
    st.set_page_config(
        page_title="SmartSync Protocol (SSP)",
        page_icon="🔄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Ensure session state is initialized
    initialize_session_state()
    
    st.title("🔄 SmartSync Protocol (SSP)")
    st.markdown("A lightweight, secure, and efficient peer-to-peer file synchronization protocol")
    
    # Add log handlers
    add_log_handler(st.session_state.server_logs)
    add_log_handler(st.session_state.client_logs)
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        
        # Shared secret
        shared_secret = st.text_input(
            "Shared Secret",
            value="default_secret_key",
            type="password",
            help="Shared secret for authentication"
        )
        
        # Network settings
        st.subheader("Network Settings")
        host = st.text_input("Host", value="localhost")
        port = st.number_input("Port", value=8888, min_value=1024, max_value=65535)
        
        # Folder selection
        st.subheader("Sync Folder")
        sync_folder = st.text_input(
            "Sync Folder Path",
            value=str(Path.home() / "SSP_Sync"),
            help="Folder to synchronize"
        )
        
        # Create folder if it doesn't exist
        if sync_folder:
            Path(sync_folder).mkdir(parents=True, exist_ok=True)
    
    # Main content area with tabs
    tab1, tab2, tab3 = st.tabs(["Server", "Client", "Monitoring"])
    
    with tab1:
        st.header("🖥️ SSP Server")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Server Control")
            
            # Server status
            if st.session_state.server_status == "STOPPED":
                status_color = "red"
            elif st.session_state.server_status == "RUNNING":
                status_color = "green"
            else:
                status_color = "orange"
            
            st.markdown(f"Status: :{status_color}[{st.session_state.server_status}]")
            
            # Server buttons
            col_start, col_stop = st.columns(2)
            
            with col_start:
                if st.button("Start Server", disabled=(st.session_state.server_status == "RUNNING")):
                    if shared_secret and sync_folder:
                        try:
                            # Check if server is already running
                            if st.session_state.server_instance is not None:
                                st.warning("Server instance already exists. Stopping previous instance.")
                                try:
                                    asyncio.run(st.session_state.server_instance.stop())
                                except:
                                    pass
                            
                            st.session_state.server_instance = SSPServer(
                                shared_secret, sync_folder, host, port
                            )
                            st.session_state.server_status = "RUNNING"
                            
                            # Start server in background thread
                            server_thread = threading.Thread(
                                target=run_server_thread,
                                args=(st.session_state.server_instance,),
                                daemon=True
                            )
                            server_thread.start()
                            
                            st.success(f"Server started on {host}:{port}")
                        except OSError as e:
                            if "10048" in str(e) or "address already in use" in str(e).lower():
                                st.error(f"Port {port} is already in use. Please choose a different port or stop the existing server.")
                            else:
                                st.error(f"Network error: {e}")
                            st.session_state.server_status = "ERROR"
                        except Exception as e:
                            st.error(f"Failed to start server: {e}")
                            st.session_state.server_status = "ERROR"
                    else:
                        st.error("Please provide shared secret and sync folder")
            
            with col_stop:
                if st.button("Stop Server", disabled=(st.session_state.server_status == "STOPPED")):
                    if st.session_state.server_instance:
                        try:
                            asyncio.run(st.session_state.server_instance.stop())
                            st.session_state.server_status = "STOPPED"
                            st.session_state.server_instance = None
                            st.success("Server stopped")
                        except Exception as e:
                            st.error(f"Failed to stop server: {e}")
        
        with col2:
            st.subheader("Server Stats")
            
            if st.session_state.server_instance:
                try:
                    server_status = st.session_state.server_instance.get_server_status()
                    
                    st.metric("Active Connections", server_status.get('active_connections', 0))
                    st.metric("Total Connections", server_status.get('stats', {}).get('total_connections', 0))
                    st.metric("Files Sent", server_status.get('stats', {}).get('files_sent', 0))
                    st.metric("Bytes Sent", f"{server_status.get('stats', {}).get('bytes_sent', 0):,}")
                    st.metric("Sync Sessions", server_status.get('stats', {}).get('sync_sessions', 0))
                    
                    # Connected clients
                    clients = server_status.get('clients', [])
                    if clients:
                        st.subheader("Connected Clients")
                        for client in clients:
                            st.text(f"• {client}")
                    
                except Exception as e:
                    st.error(f"Error getting server stats: {e}")
            else:
                st.info("Server not running")
        
        # Server logs
        st.subheader("Server Logs")
        if st.session_state.server_logs:
            log_text = "\n".join(st.session_state.server_logs[-20:])  # Show last 20 logs
            st.text_area("Server Logs", value=log_text, height=200, key="server_logs_area", label_visibility="collapsed")
        else:
            st.info("No server logs yet")
    
    with tab2:
        st.header("💻 SSP Client")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Client Control")
            
            # Server connection settings
            server_host = st.text_input("Server Host", value=host)
            server_port = st.number_input("Server Port", value=port, min_value=1024, max_value=65535)
            
            # Client status
            if st.session_state.client_status in ["DISCONNECTED", "CONNECTION_ERROR"]:
                status_color = "red"
            elif st.session_state.client_status in ["CONNECTED", "AUTHENTICATED", "SYNC_COMPLETED"]:
                status_color = "green"
            else:
                status_color = "orange"
            
            st.markdown(f"Status: :{status_color}[{st.session_state.client_status}]")
            
            # Sync button
            if st.button("Start Sync", disabled=(st.session_state.client_status == "SYNC_STARTED")):
                if shared_secret and sync_folder:
                    try:
                        st.session_state.client_instance = SSPClient(
                            shared_secret, sync_folder, server_host, server_port
                        )
                        
                        # Set callbacks
                        st.session_state.client_instance.set_status_callback(status_callback)
                        st.session_state.client_instance.set_progress_callback(progress_callback)
                        
                        # Start client sync in background thread
                        client_thread = threading.Thread(
                            target=run_client_sync_thread,
                            args=(st.session_state.client_instance,),
                            daemon=True
                        )
                        client_thread.start()
                        
                        st.success("Sync started")
                    except Exception as e:
                        st.error(f"Failed to start sync: {e}")
                else:
                    st.error("Please provide shared secret and sync folder")
        
        with col2:
            st.subheader("Sync Progress")
            
            if st.session_state.sync_progress:
                progress = st.session_state.sync_progress
                
                if progress.get('phase') == 'requesting':
                    st.info(f"Requesting {progress['files_to_request']} files")
                elif progress.get('phase') == 'receiving':
                    st.progress(progress['progress'] / 100)
                    st.text(f"Receiving: {progress['file_path']}")
                    st.text(f"Chunk {progress['chunk_index'] + 1} of {progress['total_chunks']}")
            
            # Client stats
            if st.session_state.client_instance:
                try:
                    client_status = st.session_state.client_instance.get_client_status()
                    sync_stats = st.session_state.client_instance.get_sync_stats()
                    
                    st.metric("Files Received", sync_stats.get('files_received', 0))
                    st.metric("Bytes Received", f"{sync_stats.get('bytes_received', 0):,}")
                    st.metric("Pending Requests", client_status.get('pending_requests', 0))
                    
                    if sync_stats.get('sync_duration', 0) > 0:
                        st.metric("Sync Duration", f"{sync_stats['sync_duration']:.2f}s")
                    
                except Exception as e:
                    st.error(f"Error getting client stats: {e}")
            else:
                st.info("Client not active")
        
        # Client logs
        st.subheader("Client Logs")
        if st.session_state.client_logs:
            log_text = "\n".join(st.session_state.client_logs[-20:])  # Show last 20 logs
            st.text_area("Client Logs", value=log_text, height=200, key="client_logs_area", label_visibility="collapsed")
        else:
            st.info("No client logs yet")
    
    with tab3:
        st.header("📊 Monitoring")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("File System")
            
            if sync_folder and os.path.exists(sync_folder):
                try:
                    # Scan sync folder
                    protocol = SSPProtocol(shared_secret, sync_folder)
                    file_index = protocol._scan_folder()
                    
                    st.metric("Total Files", len(file_index))
                    
                    total_size = sum(file_info.size for file_info in file_index.values())
                    st.metric("Total Size", f"{total_size:,} bytes")
                    
                    # File list
                    if file_index:
                        st.subheader("Files in Sync Folder")
                        for file_path, file_info in list(file_index.items())[:10]:  # Show first 10
                            st.text(f"📄 {file_path} ({file_info.size:,} bytes)")
                        
                        if len(file_index) > 10:
                            st.text(f"... and {len(file_index) - 10} more files")
                    
                except Exception as e:
                    st.error(f"Error scanning folder: {e}")
            else:
                st.info("Sync folder not found")
        
        with col2:
            st.subheader("System Info")
            
            st.text(f"Protocol Version: 1.0")
            st.text(f"Chunk Size: 4KB")
            st.text(f"Current Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Performance metrics
            st.subheader("Performance")
            
            if st.session_state.server_instance:
                try:
                    server_stats = st.session_state.server_instance.get_server_status().get('stats', {})
                    
                    sync_sessions = server_stats.get('sync_sessions', 0)
                    if sync_sessions > 0:
                        files_sent = server_stats.get('files_sent', 0)
                        avg_files_per_session = files_sent / sync_sessions
                        st.metric("Avg Files/Session", f"{avg_files_per_session:.1f}")
                        
                        if files_sent > 0:
                            bytes_sent = server_stats.get('bytes_sent', 0)
                            avg_file_size = bytes_sent / files_sent
                            st.metric("Avg File Size", f"{avg_file_size:,.0f} bytes")
                except Exception as e:
                    st.error(f"Error getting performance stats: {e}")
    
    # Auto-refresh
    time.sleep(1)
    st.rerun()

if __name__ == "__main__":
    main()

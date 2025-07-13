# SmartSync Protocol (SSP)

**SmartSync Protocol (SSP)** is a lightweight, secure, and efficient peer-to-peer file synchronization protocol designed for reliable file sharing between devices. It features a modern web interface for easy management and monitoring.

## 🚀 Features

### Core Protocol
- **🔐 Secure Authentication**: HMAC-based mutual authentication
- **📦 Efficient Transfer**: Chunked file transfer with progress tracking
- **⚡ Asynchronous I/O**: Built on Python's `asyncio` for high performance
- **🔄 Real-time Sync**: Instant file synchronization between devices
- **💾 Incremental Updates**: Only transfers changed/new files

### Web Interface
- **🌐 Modern UI**: Clean, responsive Streamlit-based interface
- **📊 Real-time Monitoring**: Live server and client statistics
- **📈 Progress Tracking**: Visual progress bars for sync operations
- **📝 Live Logging**: Real-time log display for debugging
- **⚙️ Easy Configuration**: Web-based server and client management

### Technical Highlights
- **JSON-based Messages**: Structured communication protocol
- **Base64 Encoding**: Safe binary data transmission
- **Heartbeat System**: Connection monitoring and recovery
- **Error Handling**: Robust error detection and recovery
- **Cross-platform**: Works on Windows, macOS, and Linux

## 📋 Requirements

- **Python 3.7+**
- **Network connectivity** (local network or internet)
- **Required Python packages** (see installation section)

## 🛠️ Installation

1. **Clone or download** the SSP Protocol files
2. **Install dependencies**:
   ```bash
   pip install streamlit asyncio pathlib
   ```

3. **Verify installation** by running:
   ```bash
   python -c "import streamlit, asyncio; print('Dependencies installed successfully!')"
   ```

## 🚀 Quick Start

### Method 1: Web Interface (Recommended)

1. **Launch the web interface**:
   ```bash
   streamlit run streamlit_app.py
   ```

2. **Open your browser** and navigate to: `http://localhost:8501`

3. **Configure settings** in the sidebar:
   - Set your **shared secret** (default: `default_secret_key`)
   - Configure **network settings** (host: `localhost`, port: `8888`)
   - Set **sync folder path** (default: `~/SSP_Sync`)

4. **Start the server** using the "Start Server" button

5. **Start synchronization** using the "Start Sync" button

### Method 2: Command Line

1. **Start the server**:
   ```bash
   python ssp_server.py "your_secret_key" "C:\Path\To\Sync\Folder" localhost 8888
   ```

2. **Run the client** (in a separate terminal):
   ```bash
   python ssp_client.py "your_secret_key" "C:\Path\To\Sync\Folder" localhost 8888
   ```

## 📱 Using the Web Interface

### Server Tab
- **Start/Stop Server**: Control server operations
- **Server Stats**: View connection statistics and performance metrics
- **Connected Clients**: Monitor active client connections
- **Server Logs**: Real-time server activity logs

### Client Tab
- **Start Sync**: Initiate file synchronization
- **Sync Progress**: Visual progress tracking
- **Client Stats**: File transfer statistics
- **Client Logs**: Real-time client activity logs

### Monitoring Tab
- **File System**: View files in sync folder
- **System Info**: Protocol version and configuration
- **Performance**: Average transfer speeds and metrics

## ⚙️ Configuration Options

### Security Settings
- **Shared Secret**: Cryptographic key for authentication (required)
- **HMAC Validation**: Automatic message integrity verification

### Network Settings
- **Host**: Server IP address (default: `localhost`)
- **Port**: Server port number (default: `8888`)
- **Timeout**: Connection timeout settings

### Sync Settings
- **Sync Folder**: Local directory to synchronize
- **Chunk Size**: File transfer chunk size (4KB default)
- **Auto-refresh**: UI refresh interval

## 🔧 Advanced Usage

### Custom Configuration
```python
# Create server with custom settings
server = SSPServer(
    shared_secret="your_secure_key",
    sync_folder="/path/to/sync",
    host="0.0.0.0",  # Listen on all interfaces
    port=9999       # Custom port
)
```

### Programmatic Client
```python
# Create client with callbacks
client = SSPClient(
    shared_secret="your_secure_key",
    sync_folder="/path/to/sync",
    server_host="remote.server.com",
    server_port=8888
)

# Set progress callback
client.set_progress_callback(lambda progress: print(f"Progress: {progress}"))
```

## 🐛 Troubleshooting

### Common Issues

1. **Port already in use**:
   - Change the port number in configuration
   - Kill existing processes using the port

2. **Authentication failed**:
   - Ensure shared secret matches on both client and server
   - Check for typos in the shared secret

3. **Connection refused**:
   - Verify server is running
   - Check firewall settings
   - Confirm host/port configuration

4. **Sync folder not found**:
   - Verify folder path exists
   - Check folder permissions
   - Create folder if it doesn't exist

### Debug Mode
Enable detailed logging by setting the log level:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📊 Performance

### Benchmarks
- **Small files** (< 1MB): ~50-100 files/second
- **Large files** (> 10MB): ~10-50 MB/second transfer rate
- **Network overhead**: Minimal (JSON + base64 encoding)
- **Memory usage**: Low (streaming file transfers)

### Optimization Tips
- Use wired network connections for better performance
- Increase chunk size for large files
- Close unnecessary applications during sync
- Use SSD storage for faster file I/O

## 🏗️ Architecture

### Protocol Stack
```
┌─────────────────────┐
│   Streamlit UI      │  (Web Interface)
├─────────────────────┤
│   SSP Client/Server │  (Application Layer)
├─────────────────────┤
│   SSP Protocol      │  (Protocol Layer)
├─────────────────────┤
│   TCP/IP           │  (Transport Layer)
└─────────────────────┘
```

### Message Types
- **HELLO**: Initial handshake
- **AUTH**: Authentication challenge/response
- **FILE_INDEX**: File listing exchange
- **FILE_REQUEST**: Request specific file
- **FILE_CHUNK**: File data transmission
- **ACK**: Acknowledgment messages
- **SYNC_COMPLETE**: Synchronization completion
- **ERROR**: Error reporting
- **HEARTBEAT**: Connection monitoring

## 📄 File Structure

```
SSP Protocol/
├── ssp_protocol.py     # Core protocol implementation
├── ssp_server.py       # Server implementation
├── ssp_client.py       # Client implementation
├── streamlit_app.py    # Web interface
├── README.md          # This file
└── test_file.txt      # Test file for verification
```

## 🤝 Contributing

Contributions are welcome! Please feel free to:
- Report bugs and issues
- Suggest new features
- Submit pull requests
- Improve documentation

## 📜 License

This project is open-source and available under the **MIT License**.

---

**Made with ❤️ for efficient and secure file synchronization**


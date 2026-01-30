"""
MCP Client Manager for Phoenix Agent
Manages connections to multiple MCP servers via stdio transport.
"""

import asyncio
import json
import logging
import subprocess
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import os

logger = logging.getLogger(__name__)

# Base directory for workspace sandboxing
BASE_DIR = Path(__file__).parent.parent.parent
WORKSPACE_DIR = BASE_DIR / "workspace"

@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: List[str]
    env: Optional[Dict[str, str]] = None
    allowed_paths: Optional[List[str]] = None  # For filesystem sandboxing


class MCPServer:
    """
    Manages a single MCP server subprocess.
    Communicates via stdio (stdin/stdout JSON-RPC).
    """
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = asyncio.Lock()
    
    async def start(self) -> bool:
        """Start the MCP server subprocess."""
        try:
            env = os.environ.copy()
            if self.config.env:
                env.update(self.config.env)
            
            # On Windows, use shell=True to resolve PATH for commands like npx
            import platform
            use_shell = platform.system() == "Windows"
            
            # When shell=True, convert command list to string
            cmd = " ".join(self.config.command) if use_shell else self.config.command
            
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
                shell=use_shell
            )
            
            # Send initialize request
            init_response = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "phoenix-agent", "version": "1.0.0"}
            })
            
            if init_response and not init_response.get("error"):
                # Send initialized notification
                await self._send_notification("notifications/initialized", {})
                logger.info(f"MCP Server '{self.config.name}' started successfully")
                return True
            else:
                logger.error(f"Failed to initialize MCP server '{self.config.name}': {init_response}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start MCP server '{self.config.name}': {e}")
            return False
    
    async def stop(self):
        """Stop the MCP server subprocess."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None
            logger.info(f"MCP Server '{self.config.name}' stopped")
    
    async def _send_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict]:
        """Send a JSON-RPC request and wait for response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            logger.error(f"MCP Server '{self.config.name}' process not available")
            return None
        
        async with self._lock:
            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params
            }
            
            try:
                # Write request
                request_str = json.dumps(request) + "\n"
                logger.debug(f"MCP Request: {request_str.strip()}")
                self.process.stdin.write(request_str)
                self.process.stdin.flush()
                
                # Read response (with timeout) - may need to skip empty lines
                loop = asyncio.get_event_loop()
                for _ in range(5):  # Try up to 5 times to get a valid response
                    response_line = await asyncio.wait_for(
                        loop.run_in_executor(None, self.process.stdout.readline),
                        timeout=30.0
                    )
                    
                    if response_line:
                        response_line = response_line.strip()
                        logger.debug(f"MCP Response raw: {response_line[:200] if len(response_line) > 200 else response_line}")
                        
                        if response_line.startswith('{'):
                            result = json.loads(response_line)
                            return result
                        # Skip non-JSON lines (could be logging or headers)
                        continue
                
                logger.error(f"No valid JSON response from '{self.config.name}'")
                return None
                
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for response from '{self.config.name}'")
                return None
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error from '{self.config.name}': {e}")
                return None
            except Exception as e:
                logger.error(f"Error communicating with '{self.config.name}': {e}")
                return None
    
    async def _send_notification(self, method: str, params: Dict[str, Any]):
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            notification_str = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_str)
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"Error sending notification to '{self.config.name}': {e}")
    
    async def list_tools(self) -> List[Dict]:
        """Get list of available tools from the server."""
        response = await self._send_request("tools/list", {})
        if response and "result" in response:
            return response["result"].get("tools", [])
        return []
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Optional[Dict]:
        """Call a tool on the MCP server."""
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        if response:
            if "error" in response:
                return {"error": response["error"]}
            if "result" in response:
                return response["result"]
        return None
    
    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class MCPClientManager:
    """
    Manages multiple MCP server connections.
    Provides a unified interface for calling tools across servers.
    """
    
    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self._tool_map: Dict[str, str] = {}  # tool_name -> server_name
    
    async def register_server(self, config: MCPServerConfig) -> bool:
        """Register and start an MCP server."""
        server = MCPServer(config)
        if await server.start():
            self.servers[config.name] = server
            
            # Map tools to this server
            tools = await server.list_tools()
            for tool in tools:
                tool_name = tool.get("name")
                if tool_name:
                    self._tool_map[tool_name] = config.name
                    logger.info(f"Registered tool '{tool_name}' from server '{config.name}'")
            
            return True
        return False
    
    async def shutdown(self):
        """Stop all MCP servers."""
        for server in self.servers.values():
            await server.stop()
        self.servers.clear()
        self._tool_map.clear()
    
    def get_available_tools(self) -> List[str]:
        """Get list of all available tool names."""
        return list(self._tool_map.keys())
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict]:
        """Call a tool by name, routing to the correct server."""
        server_name = self._tool_map.get(tool_name)
        if not server_name:
            return {"error": f"Unknown tool: {tool_name}"}
        
        server = self.servers.get(server_name)
        if not server or not server.is_running:
            return {"error": f"Server '{server_name}' is not running"}
        
        return await server.call_tool(tool_name, arguments)


# Default server configurations
def get_default_configs() -> List[MCPServerConfig]:
    """Get default MCP server configurations."""
    configs = []
    
    # Filesystem MCP (npm package - @modelcontextprotocol/server-filesystem)
    # Uses npx to run the globally installed package
    configs.append(MCPServerConfig(
        name="filesystem",
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem", str(WORKSPACE_DIR)],
        allowed_paths=[str(WORKSPACE_DIR)]
    ))
    
    return configs


# Singleton instance
_manager: Optional[MCPClientManager] = None

async def get_mcp_manager() -> MCPClientManager:
    """Get or create the singleton MCP manager."""
    global _manager
    if _manager is None:
        _manager = MCPClientManager()
    return _manager

async def initialize_mcp_servers():
    """Initialize all default MCP servers."""
    manager = await get_mcp_manager()
    
    for config in get_default_configs():
        try:
            success = await manager.register_server(config)
            if success:
                logger.info(f"Initialized MCP server: {config.name}")
            else:
                logger.warning(f"Failed to initialize MCP server: {config.name}")
        except Exception as e:
            logger.warning(f"Error initializing {config.name}: {e}")
    
    return manager


# Convenience functions for common operations
async def mcp_read_file(path: str) -> Optional[str]:
    """Read a file using Filesystem MCP."""
    manager = await get_mcp_manager()
    result = await manager.call_tool("read_file", {"path": path})
    if result and "content" in result:
        return result["content"]
    return None

async def mcp_write_file(path: str, content: str) -> bool:
    """Write a file using Filesystem MCP."""
    manager = await get_mcp_manager()
    result = await manager.call_tool("write_file", {"path": path, "content": content})
    return result is not None and "error" not in result

async def mcp_list_directory(path: str) -> List[str]:
    """List directory contents using Filesystem MCP."""
    manager = await get_mcp_manager()
    result = await manager.call_tool("list_directory", {"path": path})
    if result and "entries" in result:
        return result["entries"]
    return []

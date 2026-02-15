from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml


@dataclass
class MCPServerTool:
    name: str
    description: str = ""


@dataclass
class MCPServer:
    name: str
    type: str = "http"
    endpoint: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    working_dir: str = ""
    description: str = ""
    enabled: bool = True
    tools: list[MCPServerTool] = field(default_factory=list)
    _process: Any = None
    _lock: Any = None
    _request_id: int = 0


@dataclass
class MCPConfig:
    version: int = 1
    servers: list[MCPServer] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str, mcp_servers_dir: str | None = None) -> "MCPConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        servers = []
        servers_dir = mcp_servers_dir or os.getenv("DEEPAGENT_MCP_SERVERS_DIR", "")
        
        servers_data = data.get("servers", {})
        if servers_data is None:
            servers_data = {}
        
        for name, server_data in servers_data.items():
            tools = [
                MCPServerTool(
                    name=t.get("name", ""),
                    description=t.get("description", "")
                )
                for t in server_data.get("tools", [])
            ]
            
            args = server_data.get("args", [])
            args = [
                arg.replace("${MCP_SERVERS_DIR}", servers_dir)
                for arg in args
            ]
            
            working_dir = server_data.get("working_dir", "")
            working_dir = working_dir.replace("${MCP_SERVERS_DIR}", servers_dir)
            
            servers.append(MCPServer(
                name=name,
                type=server_data.get("type", "http"),
                endpoint=server_data.get("endpoint", ""),
                command=server_data.get("command", ""),
                args=args,
                working_dir=working_dir,
                description=server_data.get("description", ""),
                enabled=server_data.get("enabled", True),
                tools=tools,
            ))
        
        return cls(version=data.get("version", 1), servers=servers)


class MCPRegistry:
    def __init__(self, servers: list[MCPServer] | None = None) -> None:
        self.servers = {s.name: s for s in (servers or [])}
        self._initialized = False
        self._init_lock = threading.Lock()

    @classmethod
    def from_env(cls, raw: str | None) -> "MCPRegistry":
        if not raw:
            return cls([])
        data = json.loads(raw)
        servers = [MCPServer(**item) for item in data]
        return cls(servers)

    @classmethod
    def from_config(cls, config_path: str, mcp_servers_dir: str | None = None) -> "MCPRegistry":
        config = MCPConfig.from_yaml(config_path, mcp_servers_dir)
        return cls([s for s in config.servers if s.enabled])

    def initialize(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            
            for server in self.servers.values():
                if server.type == "stdio":
                    self._start_stdio_server(server)
            
            self._initialized = True

    def _start_stdio_server(self, server: MCPServer) -> None:
        if not server.command:
            raise ValueError(f"stdio server {server.name} missing command")
        
        import shutil
        cmd_path = shutil.which(server.command)
        if not cmd_path:
            raise ValueError(f"Command not found: {server.command}")
        
        cwd = server.working_dir if server.working_dir else None
        
        if cwd:
            cwd_path = Path(cwd)
            if not cwd_path.exists():
                raise ValueError(
                    f"MCP server '{server.name}' working directory not found: {cwd}\n"
                    f"Please run 'install_mcp.bat' to install MCP servers."
                )
        
        server._lock = threading.Lock()
        server._process = subprocess.Popen(
            [cmd_path] + server.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            bufsize=1,
        )
        
        self._send_mcp_initialize(server)

    def _send_mcp_initialize(self, server: MCPServer) -> None:
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "deepagent", "version": "1.0.0"}
            }
        }
        response = self._send_and_receive(server, init_request)
        
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self._send_message(server, initialized_notification)

    def _send_message(self, server: MCPServer, message: dict) -> None:
        if not server._process or not server._process.stdin:
            raise RuntimeError(f"Server {server.name} not initialized")
        msg_str = json.dumps(message) + "\n"
        server._process.stdin.write(msg_str)
        server._process.stdin.flush()

    def _send_and_receive(self, server: MCPServer, message: dict) -> dict:
        with server._lock:
            self._send_message(server, message)
            line = server._process.stdout.readline()
            if not line:
                raise RuntimeError(f"Server {server.name} closed connection")
            return json.loads(line.strip())

    def call(self, server_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        
        server = self.servers.get(server_name)
        if not server:
            raise ValueError(f"MCP server not found: {server_name}")
        
        if server.type == "stdio":
            return self._call_stdio(server, payload)
        else:
            return self._call_http_sync(server, payload)

    def _call_http_sync(self, server: MCPServer, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=30) as client:
            res = client.post(server.endpoint, json=payload)
            res.raise_for_status()
            return res.json()

    def _call_stdio(self, server: MCPServer, payload: dict[str, Any]) -> dict[str, Any]:
        with server._lock:
            server._request_id += 1
            message = {
                "jsonrpc": "2.0",
                "id": server._request_id,
                "method": "tools/call",
                "params": payload
            }
            self._send_message(server, message)
            response = self._read_response(server)
        
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        
        return response.get("result", {})

    def _read_response(self, server: MCPServer) -> dict:
        if not server._process or not server._process.stdout:
            raise RuntimeError(f"Server {server.name} not initialized")
        line = server._process.stdout.readline()
        if not line:
            raise RuntimeError(f"Server {server.name} closed connection")
        return json.loads(line.strip())

    def list_tools(self, server_name: str) -> list[dict]:
        self.initialize()
        
        server = self.servers.get(server_name)
        if not server:
            raise ValueError(f"MCP server not found: {server_name}")
        
        if server.type == "stdio":
            with server._lock:
                message = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                self._send_message(server, message)
                response = self._read_response(server)
            return response.get("result", {}).get("tools", [])
        
        return [{"name": t.name, "description": t.description} for t in server.tools]

    def shutdown(self) -> None:
        for server in self.servers.values():
            if server._process:
                server._process.terminate()
                try:
                    server._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server._process.kill()
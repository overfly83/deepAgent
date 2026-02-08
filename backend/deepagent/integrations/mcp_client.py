from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class MCPServer:
    name: str
    endpoint: str


class MCPRegistry:
    def __init__(self, servers: list[MCPServer] | None = None) -> None:
        self.servers = {s.name: s for s in (servers or [])}

    @classmethod
    def from_env(cls, raw: str | None) -> "MCPRegistry":
        if not raw:
            return cls([])
        data = json.loads(raw)
        servers = [MCPServer(**item) for item in data]
        return cls(servers)

    async def call(self, server_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        server = self.servers.get(server_name)
        if not server:
            raise ValueError(f"MCP server not found: {server_name}")
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(server.endpoint, json=payload)
            res.raise_for_status()
            return res.json()


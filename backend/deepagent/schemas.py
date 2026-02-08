from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: str | None = None
    user_id: str = Field(default="user-1")
    message: str


class TodoItem(BaseModel):
    id: str
    title: str
    status: Literal["pending", "in_progress", "done"] = "pending"


class TodoWriteRequest(BaseModel):
    thread_id: str
    todos: list[TodoItem]


class MemoryWriteRequest(BaseModel):
    user_id: str
    value: dict[str, Any]


class MemorySearchRequest(BaseModel):
    user_id: str
    query: str | None = None
    limit: int = 5


class ChatResponse(BaseModel):
    thread_id: str
    user_id: str
    reply: str
    plan: list[str] = []
    todos: list[TodoItem] = []
    memories: list[dict[str, Any]] = []

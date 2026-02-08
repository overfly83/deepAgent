from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.memory import InMemoryStore
from .config import get_settings, resolve_path


def create_checkpointer(thread_id: str) -> SqliteSaver:
    settings = get_settings()
    base = resolve_path(settings.memory_db_path)
    base.parent.mkdir(parents=True, exist_ok=True)
    db_path = base.parent / f"{thread_id}.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path.as_posix(), check_same_thread=False)
    return SqliteSaver(con)


def _store_file_path():
    settings = get_settings()
    path = resolve_path(settings.memory_store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({}), encoding="utf-8")
    return path


def _load_store(store: InMemoryStore) -> None:
    path = _store_file_path()
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    for user_id, items in raw.items():
        namespace = ns_for_user(user_id)
        for item in items:
            store.put(namespace, item["key"], item["value"])


def _persist_item(user_id: str, key: str, value: dict[str, Any]) -> None:
    path = _store_file_path()
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    items = raw.get(user_id, [])
    items.append({"key": key, "value": value})
    raw[user_id] = items
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def create_store() -> InMemoryStore:
    store = InMemoryStore()
    _load_store(store)
    return store


def ns_for_user(user_id: str) -> tuple[str, str]:
    return (user_id, "memories")


def store_put(store: InMemoryStore, user_id: str, value: dict[str, Any]) -> str:
    mem_id = str(uuid.uuid4())
    store.put(ns_for_user(user_id), mem_id, value)
    _persist_item(user_id, mem_id, value)
    return mem_id


def store_search(store: InMemoryStore, user_id: str, query: str | None = None, limit: int = 5):
    return store.search(ns_for_user(user_id), query=query, limit=limit)


def store_recent(user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    path = _store_file_path()
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    items = raw.get(user_id, [])
    if limit <= 0:
        return []
    return items[-limit:]


def store_all(user_id: str) -> list[dict[str, Any]]:
    path = _store_file_path()
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return raw.get(user_id, [])

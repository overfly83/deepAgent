from __future__ import annotations

import json

from .config import resolve_path


class SessionStore:
    def __init__(self, path: str = "./data/sessions.json") -> None:
        self.path = resolve_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({}), encoding="utf-8")

    def _load(self) -> dict[str, list[str]]:
        return json.loads(self.path.read_text(encoding="utf-8") or "{}")

    def _save(self, data: dict[str, list[str]]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, user_id: str, thread_id: str) -> None:
        data = self._load()
        threads = data.get(user_id, [])
        if thread_id not in threads:
            threads.append(thread_id)
        data[user_id] = threads
        self._save(data)

    def list(self, user_id: str) -> list[str]:
        return self._load().get(user_id, [])

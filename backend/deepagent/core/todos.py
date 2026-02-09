from __future__ import annotations

import json
from typing import Dict, List

from deepagent.common.config import resolve_path
from deepagent.common.schemas import TodoItem


class TodoStore:
    def __init__(self, file_path: str = "./data/todos.json") -> None:
        self.file_path = resolve_path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text(json.dumps({}), encoding="utf-8")

    def _load(self) -> Dict[str, List[TodoItem]]:
        raw = json.loads(self.file_path.read_text(encoding="utf-8") or "{}")
        return {
            thread_id: [TodoItem(**item) for item in items] for thread_id, items in raw.items()
        }

    def _save(self, data: Dict[str, List[TodoItem]]) -> None:
        serialized = {k: [item.model_dump() for item in v] for k, v in data.items()}
        self.file_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def get(self, thread_id: str) -> List[TodoItem]:
        return self._load().get(thread_id, [])

    def write(self, thread_id: str, items: List[TodoItem]) -> List[TodoItem]:
        data = self._load()
        data[thread_id] = items
        self._save(data)
        return items

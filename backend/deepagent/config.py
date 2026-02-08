from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    debug: bool = False
    zhipu_api_key: str | None = None
    frontend_dev_server: str = "http://localhost:5173"
    frontend_dist: str = "../frontend/dist"
    memory_db_path: str = "./data/checkpoints.db"
    memory_store_path: str = "./data/memory_store.json"
    workspace_root: str = "../"
    model_config_path: str = "./config/models.yaml"
    cors_allow_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        env=os.getenv("DEEPAGENT_ENV", "dev"),
        host=os.getenv("DEEPAGENT_HOST", "0.0.0.0"),
        port=int(os.getenv("DEEPAGENT_PORT", "8000")),
        log_level=os.getenv("DEEPAGENT_LOG_LEVEL", "info"),
        debug=os.getenv("DEEPAGENT_DEBUG", "0") in ("1", "true", "True"),
        zhipu_api_key=os.getenv("ZHIPU_API_KEY"),
        frontend_dev_server=os.getenv("DEEPAGENT_FRONTEND_DEV_SERVER", "http://localhost:5173"),
        frontend_dist=os.getenv("DEEPAGENT_FRONTEND_DIST", "../frontend/dist"),
        memory_db_path=os.getenv("DEEPAGENT_MEMORY_DB", "./data/checkpoints.db"),
        memory_store_path=os.getenv("DEEPAGENT_MEMORY_STORE", "./data/memory_store.json"),
        workspace_root=os.getenv("DEEPAGENT_WORKSPACE_ROOT", "../"),
        model_config_path=os.getenv("DEEPAGENT_MODEL_CONFIG", "./config/models.yaml"),
        cors_allow_origins=[
            origin.strip()
            for origin in os.getenv(
                "DEEPAGENT_CORS_ORIGINS", "http://localhost:5173"
            ).split(",")
            if origin.strip()
        ],
    )


def resolve_path(path: str) -> Path:
    base = Path(__file__).resolve().parents[2]
    return (base / path).resolve()

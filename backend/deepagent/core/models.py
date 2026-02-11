from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml
from langchain_community.chat_models import ChatZhipuAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from deepagent.common.config import Settings, resolve_path
from deepagent.common.logger import get_logger


@dataclass
class ModelSpec:
    provider: str
    model: str
    temperature: float = 0.3
    api_key_env: str | None = None
    base_url: str | None = None
    max_retries: int = 3
    request_timeout: float = 60.0

class ModelAdapter:
    def create(self, spec: ModelSpec, settings: Settings):
        raise NotImplementedError

class ZhipuAdapter(ModelAdapter):
    def create(self, spec: ModelSpec, settings: Settings):
        api_key = (
            settings.zhipu_api_key
            if not spec.api_key_env
            else (os.getenv(spec.api_key_env) or settings.zhipu_api_key)
        )
        if not api_key:
             # Try to get from ZHIPUAI_API_KEY env var directly as fallback
             api_key = os.getenv("ZHIPUAI_API_KEY")
        
        return ChatZhipuAI(
            model=spec.model, 
            api_key=api_key, 
            temperature=spec.temperature,
            # max_retries=spec.max_retries, # Not supported in current version
            # request_timeout=spec.request_timeout, # Not supported in current version
        )

class OpenAIAdapter(ModelAdapter):
    def create(self, spec: ModelSpec, settings: Settings):
        api_key = os.getenv(spec.api_key_env or "OPENAI_API_KEY")
        api_key_secret = SecretStr(api_key) if api_key else None
        return ChatOpenAI(
            model=spec.model,
            api_key=api_key_secret,
            base_url=spec.base_url,
            temperature=spec.temperature,
            max_retries=spec.max_retries,
            timeout=spec.request_timeout, # ChatOpenAI uses 'timeout'
        )


class ModelRouter:
    def __init__(self, specs: dict[str, ModelSpec], defaults: ModelSpec, settings: Settings):
        self.specs = specs
        self.defaults = defaults
        self.settings = settings
        self.adapters: dict[str, ModelAdapter] = {
            "zhipu": ZhipuAdapter(),
            "openai": OpenAIAdapter(),
            "doubao": OpenAIAdapter(),
        }
        self._cache: dict[str, Any] = {}

    @classmethod
    def from_config(cls, path: str, settings: Settings) -> "ModelRouter":
        full_path = resolve_path(path)
        data = yaml.safe_load(full_path.read_text(encoding="utf-8")) or {}
        defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
        default_spec = ModelSpec(
            provider=str(defaults.get("provider", "zhipu")),
            model=str(defaults.get("model", "glm-4-flash")),
            temperature=float(defaults.get("temperature", 0.3)),
            api_key_env=defaults.get("api_key_env"),
            base_url=defaults.get("base_url"),
            max_retries=int(defaults.get("max_retries", 3)),
            request_timeout=float(defaults.get("request_timeout", 60.0)),
        )
        specs: dict[str, ModelSpec] = {}
        for name, raw in (data.get("models", {}) or {}).items():
            if not isinstance(raw, dict):
                continue
            specs[name] = ModelSpec(
                provider=str(raw.get("provider", default_spec.provider)),
                model=str(raw.get("model", default_spec.model)),
                temperature=float(raw.get("temperature", default_spec.temperature)),
                api_key_env=raw.get("api_key_env", default_spec.api_key_env),
                base_url=raw.get("base_url", default_spec.base_url),
                max_retries=int(raw.get("max_retries", default_spec.max_retries)),
                request_timeout=float(raw.get("request_timeout", default_spec.request_timeout)),
            )
        return cls(specs=specs, defaults=default_spec, settings=settings)

    def get_model(self, step: str):
        if step in self._cache:
            return self._cache[step]
        spec = self.specs.get(step, self.defaults)
        adapter = self.adapters.get(spec.provider)
        if not adapter:
            logger = get_logger("deepagent.models")
            logger.warn(
                f"Unsupported provider '{spec.provider}' for step '{step}', "
                f"falling back to defaults provider '{self.defaults.provider}'"
            )
            spec = self.defaults
            adapter = self.adapters.get(spec.provider)
            if not adapter:
                raise ValueError(f"No adapter available for default provider: {spec.provider}")
        model = adapter.create(spec, self.settings)
        self._cache[step] = model
        return model

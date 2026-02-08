import os

from deepagent.agent import DeepAgent
from deepagent.config import get_settings
from deepagent.memory import store_all


def test_summary_created(monkeypatch, tmp_path):
    os.environ["DEEPAGENT_MEMORY_STORE"] = str(tmp_path / "memory.json")
    model_path = tmp_path / "models.yaml"
    model_path.write_text(
        "\n".join(
            [
                "version: 1",
                "defaults:",
                "  provider: zhipu",
                "  model: glm-4-flash",
                "  temperature: 0.3",
                "models:",
                "  chat:",
                "    provider: zhipu",
                "    model: glm-4-flash",
                "    temperature: 0.3",
                "  plan:",
                "    provider: zhipu",
                "    model: glm-4-flash",
                "    temperature: 0.1",
                "  summary:",
                "    provider: zhipu",
                "    model: glm-4-flash",
                "    temperature: 0.2",
                "  doubao_chat:",
                "    provider: doubao",
                "    model: glm-4-flash",
                "    temperature: 0.2",
                "    base_url: https://example.invalid/v1",
                "    api_key_env: DOUBAO_API_KEY",
            ]
        ),
        encoding="utf-8",
    )
    os.environ["DEEPAGENT_MODEL_CONFIG"] = str(model_path)
    get_settings.cache_clear()

    class DummyAgent:
        def invoke(self, payload, config=None):
            class Msg:
                content = "ok"

            return {"messages": [Msg()]}

    monkeypatch.setattr(DeepAgent, "_get_agent", lambda self, thread_id: DummyAgent())
    monkeypatch.setattr(DeepAgent, "_summarize_text", lambda self, turns: "summary text")

    agent = DeepAgent()
    for i in range(8):
        agent.invoke("thread-1", "user-1", f"msg {i}")

    items = store_all("user-1")
    summaries = [
        item
        for item in items
        if isinstance(item.get("value"), dict) and item["value"].get("type") == "summary"
    ]
    assert len(summaries) >= 1

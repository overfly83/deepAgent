
from deepagent.config import Settings
from deepagent.models import ModelRouter, ModelSpec


def test_model_router_from_config(tmp_path):
    config_file = tmp_path / "models.yaml"
    config_file.write_text("""
defaults:
    provider: zhipu
    model: glm-4-flash
    temperature: 0.5
    max_retries: 5
models:
    chat:
        model: glm-4
    plan:
        provider: openai
        model: gpt-4
    """, encoding="utf-8")
    
    settings = Settings()
    router = ModelRouter.from_config(str(config_file), settings)
    
    # Test Defaults
    assert router.defaults.provider == "zhipu"
    assert router.defaults.max_retries == 5
    
    # Test Overrides
    chat_spec = router.specs["chat"]
    assert chat_spec.model == "glm-4"
    assert chat_spec.provider == "zhipu" # inherited
    
    plan_spec = router.specs["plan"]
    assert plan_spec.provider == "openai"
    assert plan_spec.model == "gpt-4"

def test_model_adapter_creation():
    settings = Settings(zhipu_api_key="test_key")
    spec = ModelSpec(provider="zhipu", model="glm-4-flash", temperature=0.1)
    
    from deepagent.models import ZhipuAdapter
    adapter = ZhipuAdapter()
    model = adapter.create(spec, settings)
    
    assert model.model_name == "glm-4-flash"
    assert model.temperature == 0.1

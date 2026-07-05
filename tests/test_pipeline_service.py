"""Pipeline config tests."""

from app.services.pipeline_service import build_config


def test_build_config_routes_llm1_groq_and_llm2_openai_compatible(monkeypatch):
    monkeypatch.setenv("KEYWORD_LLM_API_KEY", "gateway-key")
    monkeypatch.setenv("KEYWORD_LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("KEYWORD_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("KEYWORD_LLM_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("KEYWORD_LLM1_PROVIDER", "groq")
    monkeypatch.setenv("KEYWORD_LLM1_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("KEYWORD_LLM2_PROVIDER", "openai-compatible")
    monkeypatch.setenv("KEYWORD_LLM2_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")

    config = build_config()

    assert config.llm1_provider == "groq"
    assert config.llm1_model == "llama-3.3-70b-versatile"
    assert config.llm1_api_key == "groq-key"
    assert config.llm1_base_url is None
    assert config.llm2_provider == "openai-compatible"
    assert config.llm2_model == "gpt-5.4-mini"
    assert config.llm2_api_key == "gateway-key"
    assert config.llm2_base_url == "https://gateway.example/v1"


def test_stage_api_key_does_not_reuse_global_key_for_different_provider(monkeypatch):
    monkeypatch.setenv("KEYWORD_LLM_API_KEY", "gateway-key")
    monkeypatch.setenv("KEYWORD_LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("KEYWORD_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("KEYWORD_LLM1_PROVIDER", "gemini")
    monkeypatch.setenv("KEYWORD_LLM1_MODEL", "gemini-3.5-flash")
    monkeypatch.delenv("KEYWORD_LLM1_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    config = build_config()

    assert config.llm1_provider == "gemini"
    assert config.llm1_api_key is None
    assert config.llm2_api_key == "gateway-key"


def test_keyword_batch_size_keeps_grouping_alias():
    new_config = build_config(keyword_batch_size=7)
    old_config = build_config(grouping_batch_size=9)

    assert new_config.keyword_batch_size == 7
    assert new_config.grouping_batch_size == 7
    assert old_config.keyword_batch_size == 9

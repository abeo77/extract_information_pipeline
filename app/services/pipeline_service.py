"""Runtime helpers for pipeline execution."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace


DEFAULT_LLM_PROVIDER = "openai-compatible"
DEFAULT_LLM_MODEL = "gpt-5.4-mini"
DEFAULT_GROQ_LLM_MODEL = "llama-3.3-70b-versatile"
DEFAULT_KEYWORD_BATCH_SIZE = 48
DEFAULT_GROUPING_BATCH_SIZE = DEFAULT_KEYWORD_BATCH_SIZE
DEFAULT_EVIDENCE_BATCH_SIZE = 50
DEFAULT_MAX_EVIDENCE_SEGMENTS_PER_GROUP = 2
DEFAULT_MAX_PARALLEL_LLM_CALLS = 3
DEFAULT_MAX_TOTAL_LLM_CALLS = 8
DEFAULT_FAST_EXACT = True
DEFAULT_COVERAGE_ENABLED = True
DEFAULT_COVERAGE_MAX_GROUPS = 5
DEFAULT_COVERAGE_MODE = "adaptive"
DEFAULT_FILTER_LOW_CONFIDENCE_GROUPS = True

SUPPORTED_LLM_PROVIDERS = ("openai-compatible", "openai", "grok", "groq", "gemini")
SUGGESTED_LLM_MODELS = ("gpt-5.4-mini", "grok-4.3", "gemini-3.5-flash")

OPENAI_COMPATIBLE_PROVIDERS = {"openai-compatible", "openai", "grok"}
PROVIDER_ALIASES = {
    "compatible": "openai-compatible",
    "openai-compatible-api": "openai-compatible",
    "xai": "grok",
    "google": "gemini",
    "google-gemini": "gemini",
}
PROVIDER_API_KEY_ENVS = {
    "openai-compatible": ("OPENAI_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "grok": ("XAI_API_KEY", "GROK_API_KEY"),
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}
PROVIDER_BASE_URL_ENVS = {
    "openai-compatible": ("OPENAI_BASE_URL",),
    "openai": ("OPENAI_BASE_URL",),
    "grok": ("XAI_BASE_URL", "GROK_BASE_URL"),
    "groq": ("GROQ_BASE_URL",),
    "gemini": ("GEMINI_BASE_URL",),
}
DEFAULT_BASE_URLS = {"grok": "https://api.x.ai/v1"}
DEFAULT_STAGE_MODELS = {"groq": DEFAULT_GROQ_LLM_MODEL}
TRUE_VALUES = {"1", "true", "yes", "y"}
FALSE_VALUES = {"0", "false", "no", "n"}


@dataclass(frozen=True)
class PipelineConfig:
    llm_provider: str = DEFAULT_LLM_PROVIDER
    llm_model: str = DEFAULT_LLM_MODEL
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm1_provider: str = DEFAULT_LLM_PROVIDER
    llm1_model: str = DEFAULT_LLM_MODEL
    llm1_api_key: str | None = None
    llm1_base_url: str | None = None
    llm2_provider: str = DEFAULT_LLM_PROVIDER
    llm2_model: str = DEFAULT_LLM_MODEL
    llm2_api_key: str | None = None
    llm2_base_url: str | None = None
    keyword_batch_size: int = DEFAULT_KEYWORD_BATCH_SIZE
    evidence_batch_size: int = DEFAULT_EVIDENCE_BATCH_SIZE
    max_evidence_segments_per_group: int = DEFAULT_MAX_EVIDENCE_SEGMENTS_PER_GROUP
    max_parallel_llm_calls: int = DEFAULT_MAX_PARALLEL_LLM_CALLS
    max_total_llm_calls: int = DEFAULT_MAX_TOTAL_LLM_CALLS
    fast_exact: bool = DEFAULT_FAST_EXACT
    coverage_enabled: bool = DEFAULT_COVERAGE_ENABLED
    coverage_max_groups: int = DEFAULT_COVERAGE_MAX_GROUPS
    coverage_mode: str = DEFAULT_COVERAGE_MODE
    filter_low_confidence_groups: bool = DEFAULT_FILTER_LOW_CONFIDENCE_GROUPS
    include_admin_sections: bool = False

    @property
    def grouping_batch_size(self) -> int:
        """Backward-compatible alias for older CLI/API callers."""
        return self.keyword_batch_size


def build_config(**overrides) -> PipelineConfig:
    provider = _provider_from(overrides, "llm_provider", "KEYWORD_LLM_PROVIDER")
    model = _text_setting(overrides, "llm_model", "KEYWORD_LLM_MODEL", DEFAULT_LLM_MODEL)
    llm1_provider = _stage_provider("LLM1", provider, overrides.get("llm1_provider"))
    llm2_provider = _stage_provider("LLM2", provider, overrides.get("llm2_provider"))

    return PipelineConfig(
        llm_provider=provider,
        llm_model=model,
        llm_api_key=_clean_optional(overrides.get("llm_api_key")) or _env_api_key(provider),
        llm_base_url=_clean_optional(overrides.get("llm_base_url")) or _env_base_url(provider),
        llm1_provider=llm1_provider,
        llm1_model=_stage_model("LLM1", llm1_provider, model, overrides.get("llm1_model")),
        llm1_api_key=_stage_api_key("LLM1", llm1_provider, provider, overrides.get("llm1_api_key")),
        llm1_base_url=_stage_base_url("LLM1", llm1_provider, overrides.get("llm1_base_url")),
        llm2_provider=llm2_provider,
        llm2_model=_stage_model("LLM2", llm2_provider, model, overrides.get("llm2_model")),
        llm2_api_key=_stage_api_key("LLM2", llm2_provider, provider, overrides.get("llm2_api_key")),
        llm2_base_url=_stage_base_url("LLM2", llm2_provider, overrides.get("llm2_base_url")),
        keyword_batch_size=_int_override(
            overrides,
            "keyword_batch_size",
            DEFAULT_KEYWORD_BATCH_SIZE,
            legacy_key="grouping_batch_size",
        ),
        evidence_batch_size=_int_override(overrides, "evidence_batch_size", DEFAULT_EVIDENCE_BATCH_SIZE),
        max_evidence_segments_per_group=_int_override(
            overrides,
            "max_evidence_segments_per_group",
            DEFAULT_MAX_EVIDENCE_SEGMENTS_PER_GROUP,
        ),
        max_parallel_llm_calls=_int_override(
            overrides,
            "max_parallel_llm_calls",
            DEFAULT_MAX_PARALLEL_LLM_CALLS,
            env_name="MAX_PARALLEL_LLM_CALLS",
            minimum=1,
        ),
        max_total_llm_calls=_int_override(
            overrides,
            "max_total_llm_calls",
            DEFAULT_MAX_TOTAL_LLM_CALLS,
            env_name="MAX_TOTAL_LLM_CALLS",
            minimum=1,
        ),
        fast_exact=_bool_override(
            overrides,
            "fast_exact",
            "KEYWORD_FAST_EXACT",
            DEFAULT_FAST_EXACT,
        ),
        coverage_enabled=_bool_override(
            overrides,
            "coverage_enabled",
            "KEYWORD_COVERAGE_ENABLED",
            DEFAULT_COVERAGE_ENABLED,
        ),
        coverage_max_groups=_int_override(
            overrides,
            "coverage_max_groups",
            DEFAULT_COVERAGE_MAX_GROUPS,
            env_name="KEYWORD_COVERAGE_MAX_GROUPS",
            minimum=0,
        ),
        coverage_mode=_coverage_mode(overrides.get("coverage_mode")),
        filter_low_confidence_groups=_bool_override(
            overrides,
            "filter_low_confidence_groups",
            "KEYWORD_FILTER_LOW_CONFIDENCE_GROUPS",
            DEFAULT_FILTER_LOW_CONFIDENCE_GROUPS,
        ),
        include_admin_sections=_include_admin(overrides.get("include_admin_sections")),
    )


def create_chat_model(config: PipelineConfig, stage: str | None = None):
    config = _stage_config(config, stage)
    if config.llm_provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM provider: {config.llm_provider}. "
            f"Use one of: {', '.join(SUPPORTED_LLM_PROVIDERS)}."
        )

    if config.llm_base_url or config.llm_provider in OPENAI_COMPATIBLE_PROVIDERS:
        return _create_openai_compatible_chat_model(config)
    if config.llm_provider == "gemini":
        return _create_gemini_chat_model(config)
    return _create_groq_chat_model(config)


class StepTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self._start


def _stage_config(config: PipelineConfig, stage: str | None) -> PipelineConfig:
    if stage not in {"llm1", "llm2"}:
        return config

    prefix = stage
    return replace(
        config,
        llm_provider=getattr(config, f"{prefix}_provider"),
        llm_model=getattr(config, f"{prefix}_model"),
        llm_api_key=getattr(config, f"{prefix}_api_key"),
        llm_base_url=getattr(config, f"{prefix}_base_url"),
    )


def _create_openai_compatible_chat_model(config: PipelineConfig):
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as error:
        raise RuntimeError("Install langchain-openai to use OpenAI-compatible endpoints.") from error

    kwargs = {
        "model": config.llm_model,
        "api_key": _require_api_key(config),
        "temperature": 0,
        "max_retries": 2,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }
    base_url = config.llm_base_url or DEFAULT_BASE_URLS.get(config.llm_provider)
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _create_gemini_chat_model(config: PipelineConfig):
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as error:
        raise RuntimeError("Install langchain-google-genai to use Gemini native endpoints.") from error

    return ChatGoogleGenerativeAI(
        model=config.llm_model,
        api_key=_require_api_key(config),
        temperature=0,
        max_retries=2,
    )


def _create_groq_chat_model(config: PipelineConfig):
    try:
        from langchain_groq import ChatGroq
    except ImportError as error:
        raise RuntimeError("Install langchain-groq to use Groq native endpoints.") from error

    return ChatGroq(
        model=config.llm_model,
        api_key=_require_api_key(config),
        temperature=0,
        max_retries=2,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _provider_from(overrides: dict, key: str, env_name: str) -> str:
    value = _clean_optional(overrides.get(key)) or os.getenv(env_name) or DEFAULT_LLM_PROVIDER
    return _normalize_provider(value)


def _stage_provider(stage: str, fallback: str, override: object) -> str:
    value = _clean_optional(override) or os.getenv(f"KEYWORD_{stage}_PROVIDER") or fallback
    return _normalize_provider(value)


def _stage_model(stage: str, provider: str, fallback: str, override: object) -> str:
    return (
        _clean_optional(override)
        or os.getenv(f"KEYWORD_{stage}_MODEL")
        or DEFAULT_STAGE_MODELS.get(provider)
        or fallback
    )


def _normalize_provider(provider: str | None) -> str:
    value = (provider or DEFAULT_LLM_PROVIDER).strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(value, value)


def _text_setting(overrides: dict, key: str, env_name: str, default: str) -> str:
    return _clean_optional(overrides.get(key)) or os.getenv(env_name) or default


def _int_override(
    overrides: dict,
    key: str,
    default: int,
    env_name: str | None = None,
    minimum: int | None = None,
    legacy_key: str | None = None,
) -> int:
    value = overrides.get(key)
    if value is None and legacy_key:
        value = overrides.get(legacy_key)
    if value is None and env_name:
        value = os.getenv(env_name)
    number = int(value if value is not None else default)
    return max(minimum, number) if minimum is not None else number


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or set(text) == {"."}:
        return None
    return text


def _env_api_key(provider: str) -> str | None:
    return _first_env(("KEYWORD_LLM_API_KEY", *PROVIDER_API_KEY_ENVS.get(provider, ())))


def _stage_api_key(
    stage: str,
    provider: str,
    default_provider: str,
    override: object,
) -> str | None:
    return (
        _clean_optional(override)
        or _first_env((f"KEYWORD_{stage}_API_KEY",))
        or _provider_native_api_key(provider)
        or (_first_env(("KEYWORD_LLM_API_KEY",)) if provider == default_provider else None)
    )


def _provider_native_api_key(provider: str) -> str | None:
    return _first_env(PROVIDER_API_KEY_ENVS.get(provider, ()))


def _env_base_url(provider: str) -> str | None:
    return _first_env(("KEYWORD_LLM_BASE_URL", *PROVIDER_BASE_URL_ENVS.get(provider, ())))


def _stage_base_url(stage: str, provider: str, override: object) -> str | None:
    return (
        _clean_optional(override)
        or _first_env((f"KEYWORD_{stage}_BASE_URL",))
        or _first_env(_stage_base_url_envs(provider))
    )


def _stage_base_url_envs(provider: str) -> tuple[str, ...]:
    if provider in {"openai-compatible", "openai"}:
        return ("OPENAI_BASE_URL", "KEYWORD_LLM_BASE_URL")
    return PROVIDER_BASE_URL_ENVS.get(provider, ())


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = _clean_optional(os.getenv(name))
        if value:
            return value
    return None


def _require_api_key(config: PipelineConfig) -> str:
    if config.llm_api_key:
        return config.llm_api_key
    raise RuntimeError("LLM API key is required. Set KEYWORD_LLM_API_KEY or a stage-specific key.")


def _include_admin(value: object | None) -> bool:
    if value is None:
        value = os.getenv("INCLUDE_ADMIN_SECTIONS", "false")
    return str(value).strip().lower() in TRUE_VALUES


def _coverage_mode(value: object | None) -> str:
    normalized = _clean_optional(value) or os.getenv("KEYWORD_COVERAGE_MODE") or DEFAULT_COVERAGE_MODE
    normalized = normalized.strip().lower()
    if normalized in {"off", "none", "disabled"}:
        return "off"
    if normalized in {"broad", "legacy"}:
        return "broad"
    return "adaptive"


def _bool_override(
    overrides: dict,
    key: str,
    env_name: str,
    default: bool,
) -> bool:
    value = overrides.get(key)
    if value is None:
        value = os.getenv(env_name)
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return bool(value)

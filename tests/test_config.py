"""Configuration tests: secrets must never show up when settings are printed (CFG-09)."""

from pydantic import SecretStr

from app.config import Settings


def test_settings_repr_hides_secret_values():
    # These are fake values made up for the test, so the S106 warning is expected here.
    settings = Settings(
        postgres_password=SecretStr("super-secret-value"), llm_api_key=SecretStr("another-secret")
    )
    text = repr(settings)
    assert "super-secret-value" not in text
    assert "another-secret" not in text


def test_llm_fallback_models_read_from_json_list(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_MODELS", '["model-b", "model-c"]')

    assert Settings().llm_fallback_models == ["model-b", "model-c"]


def test_docs_enabled_only_in_development():
    assert Settings(app_environment="development").docs_enabled is True
    assert Settings(app_environment="production").docs_enabled is False

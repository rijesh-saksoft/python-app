"""Configuration tests: secrets must never show up when settings are printed (CFG-09)."""

from app.config import Settings


def test_settings_repr_hides_secret_values():
    # These are fake values made up for the test, so the S106 warning is expected here.
    settings = Settings(postgres_password="super-secret-value", llm_api_key="another-secret")  # noqa: S106
    text = repr(settings)
    assert "super-secret-value" not in text
    assert "another-secret" not in text


def test_docs_enabled_only_in_development():
    assert Settings(app_environment="development").docs_enabled is True
    assert Settings(app_environment="production").docs_enabled is False

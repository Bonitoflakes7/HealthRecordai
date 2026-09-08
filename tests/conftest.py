import pytest

from backend.app.core import config


@pytest.fixture(autouse=True)
def disable_external_llm_for_tests(monkeypatch):
    """Keep unit/API tests deterministic and independent of provider network access."""
    monkeypatch.setattr(config.settings, "llm_model", None)
    monkeypatch.setattr(config.settings, "gemini_api_key", None)
    monkeypatch.setattr(config.settings, "auth_enabled", False)

import importlib

import pytest


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for key in (
        "APP_MODE",
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_load_runtime_settings_requires_stripe_keys_in_production(monkeypatch):
    monkeypatch.setenv("APP_MODE", "production")
    rc = importlib.import_module("runtime_config")

    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        rc.load_runtime_settings()


def test_load_runtime_settings_allows_missing_stripe_keys_in_dev(monkeypatch):
    monkeypatch.setenv("APP_MODE", "development")
    rc = importlib.import_module("runtime_config")

    settings = rc.load_runtime_settings()
    assert settings.app_mode == "development"
    assert settings.stripe_secret_key == ""


def test_google_api_key_contract(monkeypatch):
    rc = importlib.import_module("runtime_config")

    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    assert rc.load_google_api_key() == "test-google-key"

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-key")
    with pytest.raises(RuntimeError, match="deprecated"):
        rc.load_google_api_key()

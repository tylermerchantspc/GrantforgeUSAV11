"""Central runtime configuration and fail-fast validation for GrantForgeUSA."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSettings:
    app_mode: str
    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str


def _require(name: str, value: str) -> str:
    if value:
        return value
    raise RuntimeError(
        f"Missing required environment variable: {name}. "
        f"Set {name} in your runtime environment before starting the server."
    )


def _app_mode() -> str:
    return (os.getenv("APP_MODE") or "production").strip().lower()


def load_runtime_settings() -> RuntimeSettings:
    mode = _app_mode()
    stripe_secret_key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    stripe_publishable_key = (os.getenv("STRIPE_PUBLISHABLE_KEY") or "").strip()
    stripe_webhook_secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()

    if mode == "production":
        stripe_secret_key = _require("STRIPE_SECRET_KEY", stripe_secret_key)
        stripe_publishable_key = _require("STRIPE_PUBLISHABLE_KEY", stripe_publishable_key)

    return RuntimeSettings(
        app_mode=mode,
        stripe_secret_key=stripe_secret_key,
        stripe_publishable_key=stripe_publishable_key,
        stripe_webhook_secret=stripe_webhook_secret,
    )


def load_google_api_key() -> str:
    key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    legacy = (os.getenv("GEMINI_API_KEY") or "").strip()

    if key:
        return key
    if legacy:
        raise RuntimeError(
            "GEMINI_API_KEY is deprecated. Rename it to GOOGLE_API_KEY and restart."
        )

    raise RuntimeError(
        "Missing required environment variable: GOOGLE_API_KEY. "
        "Generate a replacement key, restrict it to required Google Generative Language APIs, "
        "and set GOOGLE_API_KEY in your runtime environment."
    )

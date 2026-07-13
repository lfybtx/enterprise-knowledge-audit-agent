"""Model-provider configuration with a deterministic local fallback.

The application does not call a remote model in this first integration step.
Keeping configuration separate from model calls means later embedding and chat
providers can share the same validated settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


LOCAL_PROVIDER = "local"
LOCAL_HF_PROVIDER = "local-hf"
OPENAI_COMPATIBLE_PROVIDER = "openai-compatible"
SUPPORTED_PROVIDERS = {LOCAL_PROVIDER, LOCAL_HF_PROVIDER, OPENAI_COMPATIBLE_PROVIDER}
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_EMBEDDING_DIMENSIONS = 512
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_LOCAL_CHAT_BASE_URL = "http://host.docker.internal:11434/v1"
DEFAULT_LOCAL_CHAT_MODEL = "qwen2.5:7b-instruct"


class ModelConfigurationError(ValueError):
    """Raised when a selected remote provider is missing required settings."""


@dataclass(frozen=True)
class ModelProviderSettings:
    provider: str
    api_key: str | None
    base_url: str | None
    chat_model: str | None
    embedding_model: str | None
    embedding_dimensions: int

    @classmethod
    def from_environment(cls) -> "ModelProviderSettings":
        provider = os.getenv("MODEL_PROVIDER", LOCAL_PROVIDER).strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            values = ", ".join(sorted(SUPPORTED_PROVIDERS))
            raise ModelConfigurationError(f"MODEL_PROVIDER must be one of: {values}")

        if provider == LOCAL_PROVIDER:
            return cls(
                provider=provider,
                api_key=None,
                base_url=None,
                chat_model=None,
                embedding_model=None,
                embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            )

        if provider == LOCAL_HF_PROVIDER:
            return cls(
                provider=provider,
                api_key=None,
                base_url=None,
                chat_model=None,
                embedding_model=os.getenv("LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL).strip(),
                embedding_dimensions=_embedding_dimensions_from_environment("LOCAL_EMBEDDING_DIMENSIONS"),
            )

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ModelConfigurationError("OPENAI_API_KEY is required when MODEL_PROVIDER=openai-compatible")

        return cls(
            provider=provider,
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip().rstrip("/"),
            chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini").strip(),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            embedding_dimensions=_embedding_dimensions_from_environment("OPENAI_EMBEDDING_DIMENSIONS"),
        )

    def public_status(self) -> dict[str, object]:
        """Return non-sensitive provider details that are safe for an API response."""
        return {
            "provider": self.provider,
            "remote_enabled": self.provider == OPENAI_COMPATIBLE_PROVIDER,
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
        }


@dataclass(frozen=True)
class ChatProviderSettings:
    provider: str
    api_key: str | None
    base_url: str | None
    chat_model: str | None

    @classmethod
    def from_environment(cls) -> "ChatProviderSettings":
        provider = os.getenv("CHAT_PROVIDER", LOCAL_PROVIDER).strip().lower()
        if provider not in {LOCAL_PROVIDER, OPENAI_COMPATIBLE_PROVIDER}:
            raise ModelConfigurationError("CHAT_PROVIDER must be one of: local, openai-compatible")
        if provider == LOCAL_PROVIDER:
            return cls(provider=provider, api_key=None, base_url=None, chat_model=None)

        base_url = os.getenv("CHAT_OPENAI_BASE_URL", DEFAULT_LOCAL_CHAT_BASE_URL).strip().rstrip("/")
        api_key = os.getenv("CHAT_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "ollama")).strip()
        if not api_key:
            raise ModelConfigurationError("CHAT_OPENAI_API_KEY is required when CHAT_PROVIDER=openai-compatible")
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            chat_model=os.getenv("CHAT_OPENAI_MODEL", DEFAULT_LOCAL_CHAT_MODEL).strip(),
        )

    def public_status(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "remote_enabled": self.provider == OPENAI_COMPATIBLE_PROVIDER,
            "base_url": self.base_url,
            "chat_model": self.chat_model,
            "local_endpoint": bool(self.base_url and ("localhost" in self.base_url or "host.docker.internal" in self.base_url)),
        }


def _embedding_dimensions_from_environment(variable_name: str) -> int:
    raw_value = os.getenv(variable_name, str(DEFAULT_EMBEDDING_DIMENSIONS)).strip()
    try:
        dimensions = int(raw_value)
    except ValueError as error:
        raise ModelConfigurationError(f"{variable_name} must be an integer") from error
    if dimensions != DEFAULT_EMBEDDING_DIMENSIONS:
        raise ModelConfigurationError(
            f"{variable_name} must be {DEFAULT_EMBEDDING_DIMENSIONS} to match the current pgvector schema"
        )
    return dimensions

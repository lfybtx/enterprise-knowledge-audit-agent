from app.services.model_provider import ChatProviderSettings, ModelConfigurationError, ModelProviderSettings


def test_local_provider_is_the_default(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = ModelProviderSettings.from_environment()

    assert settings.provider == "local"
    assert settings.public_status()["remote_enabled"] is False
    assert settings.api_key is None


def test_openai_compatible_provider_reads_non_sensitive_status(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:1234/v1/")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "test-chat")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "test-embedding")

    status = ModelProviderSettings.from_environment().public_status()

    assert status == {
        "provider": "openai-compatible",
        "remote_enabled": True,
        "chat_model": "test-chat",
        "embedding_model": "test-embedding",
        "embedding_dimensions": 512,
    }
    assert "test-key" not in str(status)


def test_remote_provider_requires_an_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        ModelProviderSettings.from_environment()
    except ModelConfigurationError as error:
        assert "OPENAI_API_KEY" in str(error)
    else:
        raise AssertionError("Expected a configuration error")


def test_local_chat_provider_is_the_default(monkeypatch):
    monkeypatch.delenv("CHAT_PROVIDER", raising=False)
    monkeypatch.delenv("CHAT_OPENAI_API_KEY", raising=False)

    settings = ChatProviderSettings.from_environment()

    assert settings.provider == "local"
    assert settings.api_key is None
    assert settings.public_status()["remote_enabled"] is False


def test_openai_compatible_chat_provider_reads_non_sensitive_status(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai-compatible")
    monkeypatch.setenv("CHAT_OPENAI_API_KEY", "chat-secret")
    monkeypatch.setenv("CHAT_OPENAI_BASE_URL", "http://host.docker.internal:11434/v1/")
    monkeypatch.setenv("CHAT_OPENAI_MODEL", "qwen2.5:7b-instruct")

    status = ChatProviderSettings.from_environment().public_status()

    assert status == {
        "provider": "openai-compatible",
        "remote_enabled": True,
        "base_url": "http://host.docker.internal:11434/v1",
        "chat_model": "qwen2.5:7b-instruct",
        "local_endpoint": True,
    }
    assert "chat-secret" not in str(status)


def test_openai_compatible_chat_provider_can_use_default_ollama_key(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai-compatible")
    monkeypatch.delenv("CHAT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CHAT_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("CHAT_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = ChatProviderSettings.from_environment()

    assert settings.api_key == "ollama"
    assert settings.base_url == "http://host.docker.internal:11434/v1"
    assert settings.chat_model == "qwen2.5:7b-instruct"

from unittest.mock import patch
import httpx
import pytest
from app.config import Settings
from app.models import Model, ProviderError


@pytest.mark.parametrize("provider,payload", [
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "Policy answer [doc:1]"}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}),
    ("ollama", {"message": {"content": "Policy answer [doc:1]"}, "prompt_eval_count": 10,
                "eval_count": 5})])
def test_provider_contracts(provider, payload):
    settings = Settings(provider=provider, model="test-model", gemini_api_key="fake-test-key", _env_file=None)
    def respond(url, **kwargs):
        assert "secret" not in str(kwargs["json"])
        assert "evidence" in str(kwargs["json"])
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))
    with patch("httpx.Client.post", side_effect=respond):
        result = Model(settings).generate("question", [{"id": "doc:1", "text": "Policy"}], "protected")
    assert result == {"text": "Policy answer [doc:1]", "input_tokens": 10, "output_tokens": 5}


def test_bounded_transient_retries():
    model = Model(Settings(provider="ollama", model="test-model", _env_file=None))
    def unavailable(url, **kwargs):
        return httpx.Response(503, request=httpx.Request("POST", url))
    with patch("httpx.Client.post", side_effect=unavailable) as post, patch("app.models.time.sleep"):
        with pytest.raises(ProviderError):
            model.generate("question", [], "baseline")
        assert post.call_count == 3


def test_configuration_fails_closed():
    with pytest.raises(ValueError):
        Model(Settings(provider="gemini", model="test-model", gemini_api_key="", _env_file=None))
    with pytest.raises(ValueError):
        Model(Settings(provider="ollama", model="extractive-v1", _env_file=None))

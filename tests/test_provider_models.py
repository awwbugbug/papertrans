import httpx
import pytest

from papertrans.translation.models import list_provider_models


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lists_deepseek_models_sorted_and_deduplicated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.deepseek.com/models"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "deepseek-v4-flash"},
                    {"id": "deepseek-chat"},
                    {"id": "deepseek-chat"},
                ]
            },
        )

    models = list_provider_models("deepseek", "sk-test", http_client=_client(handler))
    assert models == ["deepseek-chat", "deepseek-v4-flash"]


def test_kimi_uses_versioned_base_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.moonshot.cn/v1/models"
        return httpx.Response(200, json={"data": [{"id": "kimi-k2.6"}]})

    models = list_provider_models("kimi", "sk", http_client=_client(handler))
    assert models == ["kimi-k2.6"]


def test_zhipu_uses_bigmodel_base_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://open.bigmodel.cn/api/coding/paas/v4/models"
        return httpx.Response(200, json={"data": [{"id": "glm-4.6"}, {"id": "glm-4-flash"}]})

    models = list_provider_models("zhipu", "sk", http_client=_client(handler))
    assert models == ["glm-4-flash", "glm-4.6"]


def test_compatible_lists_from_provided_base_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.example.com/v1/models"
        return httpx.Response(200, json={"data": [{"id": "gpt-x"}]})

    models = list_provider_models(
        "compatible", "k", "https://api.example.com/v1", http_client=_client(handler)
    )
    assert models == ["gpt-x"]


def test_missing_api_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        list_provider_models("deepseek", "")


def test_mock_provider_is_unsupported() -> None:
    with pytest.raises(ValueError):
        list_provider_models("mock", "k")


def test_compatible_requires_valid_base_url() -> None:
    # Base-URL validation happens before any network call.
    with pytest.raises(ValueError):
        list_provider_models("compatible", "k", "not-a-url")


def test_unauthorized_raises_value_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(ValueError):
        list_provider_models("kimi", "bad", http_client=_client(handler))


def test_server_error_raises_runtime_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    with pytest.raises(RuntimeError):
        list_provider_models("deepseek", "k", http_client=_client(handler))


def test_empty_model_list_raises_runtime_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(RuntimeError):
        list_provider_models("deepseek", "k", http_client=_client(handler))

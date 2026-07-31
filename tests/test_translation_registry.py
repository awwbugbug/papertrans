import httpx
import pytest

from papertrans.translation import MockTranslationProvider
from papertrans.translation.deepseek import DeepSeekTranslationProvider
from papertrans.translation.kimi import KimiTranslationProvider
from papertrans.translation.registry import create_translation_provider


def test_registry_creates_mock_without_credentials() -> None:
    provider = create_translation_provider(
        "mock", length_factor=1.25, environ={}
    )

    assert isinstance(provider, MockTranslationProvider)
    assert provider.length_factor == 1.25


def test_registry_creates_named_providers_from_expected_environment() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    deepseek = create_translation_provider(
        "deepseek",
        environ={"DEEPSEEK_API_KEY": "deepseek-sentinel"},
        http_client=client,
    )
    kimi = create_translation_provider(
        "kimi",
        model="kimi-k2.6",
        environ={"MOONSHOT_API_KEY": "kimi-sentinel"},
        http_client=client,
    )

    assert isinstance(deepseek, DeepSeekTranslationProvider)
    assert isinstance(kimi, KimiTranslationProvider)
    assert deepseek.cache_identity["model"] == "deepseek-v4-flash"
    assert kimi.cache_identity["model"] == "kimi-k2.6"
    assert "sentinel" not in str(deepseek.cache_identity)
    assert "sentinel" not in str(kimi.cache_identity)


def test_compatible_requires_endpoint_model_and_environment_key() -> None:
    with pytest.raises(ValueError, match="--base-url"):
        create_translation_provider("compatible", model="custom", environ={})
    with pytest.raises(ValueError, match="--model"):
        create_translation_provider(
            "compatible", base_url="https://example.test/v1", environ={}
        )
    with pytest.raises(ValueError, match="PAPERTRANS_COMPATIBLE_API_KEY") as exc_info:
        create_translation_provider(
            "compatible",
            base_url="https://example.test/v1",
            model="custom",
            environ={},
        )

    assert "sk-" not in str(exc_info.value)


def test_named_provider_rejects_compatible_only_options() -> None:
    with pytest.raises(ValueError, match="only valid with compatible"):
        create_translation_provider(
            "deepseek",
            base_url="https://relay.test/v1",
            environ={"DEEPSEEK_API_KEY": "key"},
        )

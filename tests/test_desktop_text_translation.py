from pathlib import Path

from papertrans.desktop.text_translation import (
    TEXT_TRANSLATION_MODE_SELECTION,
    DesktopTextTranslationRequest,
    DesktopTextTranslator,
)
from papertrans.translation import TranslationResult


class _ExternalProvider:
    name = "deepseek"
    cache_identity = {"provider": "deepseek", "model": "fixture"}

    def translate(self, requests):  # type: ignore[no-untyped-def]
        return [
            TranslationResult(
                segment_id=request.segment_id,
                normal=f"安全译文{''.join(request.protected_tokens)}",
                compact=f"简洁译文{''.join(request.protected_tokens)}",
                provider=self.name,
            )
            for request in requests
        ]


def test_text_translator_reuses_protection_and_reliable_cache(tmp_path: Path) -> None:
    translator = DesktopTextTranslator(tmp_path / "cache")
    request = DesktopTextTranslationRequest(
        text="See [12], https://example.com and 10 ms for details.",
        provider="mock",
    )

    first = translator.translate(request)
    second = translator.translate(request)

    assert "[12]" in first["translation"]
    assert "https://example.com" in first["translation"]
    assert "10 ms" in first["translation"]
    assert first["protection"] == {"tokenCount": 3, "passed": True}
    assert first["providerExecution"]["provider_calls"] == 1
    assert second["translation"] == first["translation"]
    assert second["providerExecution"]["cache_hits"] == 1
    assert second["providerExecution"]["provider_calls"] == 0


def test_text_translator_requires_explicit_external_credentials(tmp_path: Path) -> None:
    translator = DesktopTextTranslator(tmp_path / "cache")

    try:
        translator.translate(
            DesktopTextTranslationRequest(text="Hello", provider="deepseek")
        )
    except ValueError as exc:
        assert "API Key" in str(exc)
    else:
        raise AssertionError("missing external provider key should fail")


def test_text_translator_does_not_persist_source_or_session_key(tmp_path: Path) -> None:
    captured_environment: dict[str, str] = {}

    def provider_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_environment.update(kwargs["environ"])
        return _ExternalProvider()

    translator = DesktopTextTranslator(
        tmp_path / "cache",
        provider_factory=provider_factory,
    )
    secret = "desktop-session-secret"
    source = "Unpublished result [3]"

    result = translator.translate(
        DesktopTextTranslationRequest(text=source, provider="deepseek"),
        api_key=secret,
    )

    assert result["translation"] == "安全译文[3]"
    assert captured_environment == {"DEEPSEEK_API_KEY": secret}
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "cache").rglob("*.json")
    )
    assert secret not in persisted
    assert source not in persisted


def test_selected_text_uses_an_isolated_cache_context(tmp_path: Path) -> None:
    translator = DesktopTextTranslator(tmp_path / "cache")
    source = "proposal [4]"

    standalone = translator.translate(DesktopTextTranslationRequest(text=source))
    selected = translator.translate(
        DesktopTextTranslationRequest(
            text=source,
            translation_mode=TEXT_TRANSLATION_MODE_SELECTION,
        )
    )
    selected_cached = translator.translate(
        DesktopTextTranslationRequest(
            text=source,
            translation_mode=TEXT_TRANSLATION_MODE_SELECTION,
        )
    )

    assert standalone["providerExecution"]["provider_calls"] == 1
    assert selected["providerExecution"]["provider_calls"] == 1
    assert selected_cached["providerExecution"]["provider_calls"] == 0
    assert selected_cached["providerExecution"]["cache_hits"] == 1

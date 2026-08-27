from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from papertrans.desktop.jobs import (
    DESKTOP_PROVIDER_KEY_NAMES,
    DESKTOP_PROVIDER_LABELS,
    ProviderFactory,
)
from papertrans.translation import (
    CloseableTranslationProvider,
    ProtectedTokenError,
    ReliableTranslationProvider,
    RetryPolicy,
    TranslationProvider,
    TranslationRequest,
    create_translation_provider,
    protect_text,
    restore_text,
)
from papertrans.translation.prompt import SELECTION_PROMPT_VERSION, TEXT_PROMPT_VERSION

MAX_TEXT_TRANSLATION_CHARS = 20_000
MAX_SELECTED_TRANSLATION_CHARS = 300
TEXT_TRANSLATION_MODE_STANDALONE = "standalone_text"
TEXT_TRANSLATION_MODE_SELECTION = "selected_text"
_TEXT_TRANSLATION_MODES = {
    TEXT_TRANSLATION_MODE_STANDALONE,
    TEXT_TRANSLATION_MODE_SELECTION,
}


@dataclass(frozen=True, slots=True)
class DesktopTextTranslationRequest:
    text: str
    provider: str = "mock"
    model: str | None = None
    base_url: str | None = None
    source_language: str = "auto"
    target_language: str = "zh-CN"
    translation_mode: str = TEXT_TRANSLATION_MODE_STANDALONE


class DesktopTextTranslator:
    def __init__(
        self,
        cache_root: str | Path,
        *,
        provider_factory: ProviderFactory = create_translation_provider,
    ) -> None:
        self.cache_root = Path(cache_root).expanduser().resolve()
        self._provider_factory = provider_factory

    def translate(
        self,
        request: DesktopTextTranslationRequest,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        self._validate_request(request, api_key)
        provider: TranslationProvider | None = None
        try:
            provider = self._provider_factory(
                request.provider,
                model=request.model,
                base_url=request.base_url,
                environ=self._credential_environment(request.provider, api_key),
            )
            reliable = ReliableTranslationProvider(
                provider,
                self.cache_root / request.provider,
                retry_policy=RetryPolicy(max_attempts=3),
            )
            selected_text = request.translation_mode == TEXT_TRANSLATION_MODE_SELECTION
            segment = protect_text(
                "desktop-selection" if selected_text else "desktop-text",
                request.text,
            )
            results = reliable.translate(
                [
                    TranslationRequest(
                        segment_id=segment.segment_id,
                        text=segment.protected_text,
                        source_language=request.source_language,
                        target_language=request.target_language,
                        protected_tokens=tuple(
                            token.placeholder for token in segment.tokens
                        ),
                        context={
                            "schema_version": (
                                "m7_selection_v1" if selected_text else "m7_text_v1"
                            ),
                            "translation_mode": request.translation_mode,
                            "prompt_version": (
                                SELECTION_PROMPT_VERSION
                                if selected_text
                                else TEXT_PROMPT_VERSION
                            ),
                        },
                    )
                ]
            )
            if len(results) != 1:
                raise RuntimeError("Translation provider returned an invalid text result")
            result = results[0]
            translation, validation = restore_text(result.normal, segment, "normal")
            if not validation.passed:
                raise ProtectedTokenError(validation)
            compact_translation = None
            if result.compact is not None:
                compact_translation, compact_validation = restore_text(
                    result.compact,
                    segment,
                    "compact",
                )
                if not compact_validation.passed:
                    raise ProtectedTokenError(compact_validation)
            return {
                "translation": translation,
                "compactTranslation": compact_translation,
                "provider": result.provider,
                "characterCount": len(request.text),
                "protection": {
                    "tokenCount": len(segment.tokens),
                    "passed": True,
                },
                "providerExecution": reliable.stats.to_dict(),
            }
        finally:
            if isinstance(provider, CloseableTranslationProvider):
                try:
                    provider.close()
                except Exception:
                    pass

    @staticmethod
    def _validate_request(
        request: DesktopTextTranslationRequest,
        api_key: str | None,
    ) -> None:
        if not request.text.strip():
            raise ValueError("请输入需要翻译的文本")
        if len(request.text) > MAX_TEXT_TRANSLATION_CHARS:
            raise ValueError(f"单次文本翻译不能超过 {MAX_TEXT_TRANSLATION_CHARS} 个字符")
        if (
            request.translation_mode == TEXT_TRANSLATION_MODE_SELECTION
            and len(request.text) > MAX_SELECTED_TRANSLATION_CHARS
        ):
            raise ValueError(
                f"单次所选文本翻译不能超过 {MAX_SELECTED_TRANSLATION_CHARS} 个字符"
            )
        if request.translation_mode not in _TEXT_TRANSLATION_MODES:
            raise ValueError("不支持所选文本翻译模式")
        if request.provider not in DESKTOP_PROVIDER_LABELS:
            raise ValueError("不支持所选翻译服务")
        if request.provider != "mock" and not api_key:
            raise ValueError("所选翻译服务需要 API Key")
        if request.provider == "compatible" and (
            not request.base_url or not request.model
        ):
            raise ValueError("兼容接口需要 API 地址和模型名称")
        if not request.source_language.strip() or not request.target_language.strip():
            raise ValueError("源语言和目标语言不能为空")

    @staticmethod
    def _credential_environment(
        provider: str,
        api_key: str | None,
    ) -> dict[str, str]:
        if provider == "mock":
            return {}
        assert api_key is not None
        return {DESKTOP_PROVIDER_KEY_NAMES[provider]: api_key}

from __future__ import annotations

import httpx

from papertrans.translation.compatible_client import ChatCompletionsTranslationProvider
from papertrans.translation.profiles import ZHIPU_PROFILE


class ZhipuTranslationProvider(ChatCompletionsTranslationProvider):
    def __init__(
        self,
        api_key: str,
        model: str = ZHIPU_PROFILE.default_model,
        timeout_seconds: float = 60.0,
        max_output_tokens: int = 2048,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            ZHIPU_PROFILE,
            api_key,
            model,
            timeout_seconds,
            max_output_tokens,
            http_client,
        )

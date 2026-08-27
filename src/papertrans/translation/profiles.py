from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from papertrans.translation import prompt
from papertrans.translation.base import TranslationUsage


@dataclass(frozen=True, slots=True)
class ProviderPricing:
    cached_input_per_million: float
    uncached_input_per_million: float
    output_per_million: float
    currency: str
    snapshot: str

    def estimate(self, usage: TranslationUsage) -> float:
        million = Decimal(1_000_000)
        cost = (
            Decimal(usage.cached_input_tokens)
            * Decimal(str(self.cached_input_per_million))
            + Decimal(usage.uncached_input_tokens)
            * Decimal(str(self.uncached_input_per_million))
            + Decimal(usage.output_tokens) * Decimal(str(self.output_per_million))
        ) / million
        return round(float(cost), 12)


DEEPSEEK_PRICING = ProviderPricing(0.0028, 0.14, 0.28, "USD", "2026-07-31")
KIMI_PRICING = ProviderPricing(1.10, 6.50, 27.00, "CNY", "2026-07-31")


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    provider: str
    base_url: str
    default_model: str
    api_key_env: str
    thinking_mode: str
    pricing: ProviderPricing | None = None

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def request_overrides(self) -> Mapping[str, object]:
        if self.thinking_mode == "disabled":
            return MappingProxyType({"thinking": MappingProxyType({"type": "disabled"})})
        return MappingProxyType({})

    def cache_identity(self, model: str) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url.rstrip("/"),
            "model": model,
            "thinking_mode": self.thinking_mode,
            "prompt_version": prompt.PROMPT_VERSION,
            "pricing_snapshot": self.pricing.snapshot if self.pricing else None,
        }


DEEPSEEK_PROFILE = ProviderProfile(
    provider="deepseek",
    base_url="https://api.deepseek.com",
    default_model="deepseek-v4-flash",
    api_key_env="DEEPSEEK_API_KEY",
    thinking_mode="disabled",
    pricing=DEEPSEEK_PRICING,
)
KIMI_PROFILE = ProviderProfile(
    provider="kimi",
    base_url="https://api.moonshot.cn/v1",
    default_model="kimi-k2.6",
    api_key_env="MOONSHOT_API_KEY",
    thinking_mode="disabled",
    pricing=KIMI_PRICING,
)


ZHIPU_PROFILE = ProviderProfile(
    provider="zhipu",
    base_url="https://open.bigmodel.cn/api/paas/v4",
    default_model="glm-4.6",
    api_key_env="ZHIPUAI_API_KEY",
    thinking_mode="provider_default",
)


def compatible_profile(base_url: str, api_key_env: str) -> ProviderProfile:
    return ProviderProfile(
        provider="compatible",
        base_url=base_url.rstrip("/"),
        default_model="",
        api_key_env=api_key_env,
        thinking_mode="provider_default",
    )

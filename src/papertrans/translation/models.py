from __future__ import annotations

import httpx

from papertrans.translation.profiles import DEEPSEEK_PROFILE, KIMI_PROFILE, ZHIPU_PROFILE
from papertrans.translation.registry import _is_absolute_http_url

MODEL_LISTING_PROVIDERS = frozenset({"deepseek", "kimi", "zhipu", "compatible"})


def _models_base_url(provider: str, base_url: str | None) -> str:
    if provider == "deepseek":
        return DEEPSEEK_PROFILE.base_url.rstrip("/")
    if provider == "kimi":
        return KIMI_PROFILE.base_url.rstrip("/")
    if provider == "zhipu":
        return ZHIPU_PROFILE.base_url.rstrip("/")
    if not base_url or not _is_absolute_http_url(base_url):
        raise ValueError("兼容接口需要有效的 API 地址")
    return base_url.rstrip("/")


def _parse_models_response(response: httpx.Response) -> list[str]:
    if response.status_code in (401, 403):
        raise ValueError("API Key 无效或没有访问权限")
    if response.status_code == 404:
        raise RuntimeError("该服务未提供模型列表接口")
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"翻译服务返回错误（HTTP {response.status_code}）")
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("翻译服务返回了无法解析的响应") from None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("翻译服务未返回模型列表")
    seen: set[str] = set()
    models: list[str] = []
    for item in data:
        identifier = item.get("id") if isinstance(item, dict) else None
        if isinstance(identifier, str) and identifier.strip():
            name = identifier.strip()
            if name not in seen:
                seen.add(name)
                models.append(name)
    if not models:
        raise RuntimeError("翻译服务未返回任何可用模型")
    return sorted(models)


def list_provider_models(
    provider: str,
    api_key: str,
    base_url: str | None = None,
    *,
    timeout_seconds: float = 15.0,
    http_client: httpx.Client | None = None,
) -> list[str]:
    """Fetch the model ids an OpenAI-compatible provider advertises at ``/models``."""
    provider = provider.lower()
    if provider not in MODEL_LISTING_PROVIDERS:
        raise ValueError("该翻译服务不支持自动检测模型")
    if not api_key:
        raise ValueError("请先填写 API Key")
    url = f"{_models_base_url(provider, base_url)}/models"

    def _fetch(client: httpx.Client) -> list[str]:
        try:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.RequestError):
            raise RuntimeError("无法连接到翻译服务，请检查网络或 API 地址") from None
        return _parse_models_response(response)

    if http_client is not None:
        return _fetch(http_client)
    with httpx.Client() as owned_client:
        return _fetch(owned_client)

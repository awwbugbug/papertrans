from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx

from papertrans.translation.base import TranslationProvider
from papertrans.translation.compatible_client import ChatCompletionsTranslationProvider
from papertrans.translation.deepseek import DeepSeekTranslationProvider
from papertrans.translation.kimi import KimiTranslationProvider
from papertrans.translation.mock import MockTranslationProvider
from papertrans.translation.profiles import (
    DEEPSEEK_PROFILE,
    KIMI_PROFILE,
    compatible_profile,
)

PROVIDER_NAMES = ("mock", "deepseek", "kimi", "compatible")
_COMPATIBLE_API_KEY_ENV = "PAPERTRANS_COMPATIBLE_API_KEY"
_BRACKETED_AUTHORITY = re.compile(r"^\[[^\[\]]+\](?::\d+)?$")
_UNBRACKETED_AUTHORITY = re.compile(r"^[^:\[\]]+(?::\d+)?$")


def create_translation_provider(
    name: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    length_factor: float = 1.0,
    timeout_seconds: float = 60.0,
    max_output_tokens: int = 2048,
    environ: Mapping[str, str] | None = None,
    http_client: httpx.Client | None = None,
) -> TranslationProvider:
    provider_name = name.lower()
    if provider_name not in PROVIDER_NAMES:
        raise ValueError(f"Unknown translation provider: {name}")
    if provider_name == "mock":
        _reject_compatible_options(base_url, api_key_env)
        return MockTranslationProvider(length_factor=length_factor)
    if provider_name == "compatible":
        return _create_compatible_provider(
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            environ=environ,
            http_client=http_client,
        )

    _reject_compatible_options(base_url, api_key_env)
    environment = os.environ if environ is None else environ
    if provider_name == "deepseek":
        return DeepSeekTranslationProvider(
            _required_api_key(environment, "DEEPSEEK_API_KEY"),
            model=model or DEEPSEEK_PROFILE.default_model,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            http_client=http_client,
        )
    return KimiTranslationProvider(
        _required_api_key(environment, "MOONSHOT_API_KEY"),
        model=model or KIMI_PROFILE.default_model,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
        http_client=http_client,
    )


def _create_compatible_provider(
    *,
    model: str | None,
    base_url: str | None,
    api_key_env: str | None,
    timeout_seconds: float,
    max_output_tokens: int,
    environ: Mapping[str, str] | None,
    http_client: httpx.Client | None,
) -> ChatCompletionsTranslationProvider:
    if base_url is None:
        raise ValueError("--base-url is required for compatible")
    if not _is_absolute_http_url(base_url):
        raise ValueError("--base-url must be an absolute http or https URL")
    if not model:
        raise ValueError("--model is required for compatible")
    environment = os.environ if environ is None else environ
    key_name = api_key_env or _COMPATIBLE_API_KEY_ENV
    return ChatCompletionsTranslationProvider(
        compatible_profile(base_url, key_name),
        _required_api_key(environment, key_name),
        model,
        timeout_seconds,
        max_output_tokens,
        http_client,
    )


def _reject_compatible_options(
    base_url: str | None, api_key_env: str | None
) -> None:
    if base_url is not None or api_key_env is not None:
        raise ValueError("--base-url and --api-key-env are only valid with compatible")


def _required_api_key(environment: Mapping[str, str], key_name: str) -> str:
    api_key = environment.get(key_name)
    if not api_key:
        raise ValueError(f"Environment variable {key_name} is required")
    return api_key


def _is_absolute_http_url(value: str) -> bool:
    if any(
        character.isspace() or unicodedata.category(character) == "Cc"
        for character in value
    ):
        return False
    try:
        parsed = urlsplit(value)
        if not _has_valid_authority(parsed.netloc):
            return False
        hostname = parsed.hostname
        _port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _has_valid_authority(authority: str) -> bool:
    if authority.startswith("["):
        return _BRACKETED_AUTHORITY.fullmatch(authority) is not None
    return _UNBRACKETED_AUTHORITY.fullmatch(authority) is not None

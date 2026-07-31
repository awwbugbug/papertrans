# Multi-Provider Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `mock`, `deepseek`, `kimi`, and advanced `compatible` provider selection while preserving protected content, resumability, layout quality, and auditable usage reporting.

**Architecture:** Keep the existing provider-independent translation boundary. Add a shared non-streaming Chat Completions client, versioned prompts, vendor profiles, lightweight named adapters, and a registry; then refactor the mock-only PDF workflow into one provider-neutral job runner. The existing reliability wrapper remains responsible for per-segment cache, retry, rate limiting, and resume.

**Tech Stack:** Python 3.11+, PyMuPDF, httpx 0.28+, dataclasses, argparse, pytest 8, Ruff

## Global Constraints

- Support Python 3.11 or newer.
- Do not automatically download OCR, translation, vision-language, or embedding models.
- API keys are read only from environment variables and never enter code, CLI arguments, logs, cache keys, exceptions, or job artifacts.
- External providers receive one protected text segment per request; never upload the whole PDF.
- Do not implement automatic provider failover.
- `mock` remains the default, so external transmission is always explicit.
- One provider request returns both `normal` and `compact` strings as a JSON object.
- Every successful segment is atomically cached; invalid protection output never reaches layout.
- Tests must not call a paid or live provider.
- Preserve the existing module boundaries defined in `AGENTS.md`.
- Before handoff, run `.\.venv\Scripts\python -m pytest` and `.\.venv\Scripts\python -m ruff check .`.

---

## File Structure

### New files

- `src/papertrans/translation/profiles.py`: immutable provider profiles and dated pricing tables.
- `src/papertrans/translation/prompt.py`: versioned provider-independent academic translation prompt.
- `src/papertrans/translation/compatible_client.py`: shared httpx Chat Completions implementation.
- `src/papertrans/translation/deepseek.py`: DeepSeek adapter using the shared client.
- `src/papertrans/translation/kimi.py`: Kimi adapter using the shared client.
- `src/papertrans/translation/registry.py`: provider selection and environment-only credential validation.
- `src/papertrans/translation_job.py`: provider-neutral extraction-to-PDF workflow.
- `tests/test_translation_profiles.py`: profile, pricing, and prompt tests.
- `tests/test_translation_compatible.py`: HTTP contract, parsing, errors, and credential-safety tests.
- `tests/test_translation_registry.py`: registry and configuration tests.
- `tests/test_translation_job.py`: generic workflow and cache-resume tests.
- `tests/test_cli.py`: CLI selection and argument-scope tests.
- `tests/test_provider_translation_pipeline.py`: mock-HTTP PDF integration and secret scan.

### Modified files

- `pyproject.toml`: add the bounded httpx runtime dependency.
- `src/papertrans/translation/base.py`: add normalized per-call usage to translation results.
- `src/papertrans/translation/protection.py`: expose shared placeholder issue analysis.
- `src/papertrans/translation/reliability.py`: sanitize provider errors and aggregate fresh-call usage.
- `src/papertrans/translation/pipeline.py`: preserve usage metadata while restoring text.
- `src/papertrans/translation/__init__.py`: export the new public translation interfaces.
- `src/papertrans/mock_translation.py`: retain a backward-compatible wrapper over the generic runner.
- `src/papertrans/cli.py`: add provider configuration and invoke the registry plus generic runner.
- `tests/test_translation_reliability.py`: cover usage, failed-attempt usage, and cache billing behavior.
- `tests/test_translation_protection.py`: cover shared placeholder diagnostics.
- `tests/test_mock_translation_pipeline.py`: assert compatibility wrapper behavior.
- `README.md`, `docs/BUILD_FLOW.md`, `AGENTS.md`: document and mark M4.3 complete only after all gates pass.

---

### Task 1: Normalized Usage, Sanitized Errors, and Reliability Accounting

**Files:**
- Modify: `src/papertrans/translation/base.py`
- Modify: `src/papertrans/translation/reliability.py`
- Modify: `src/papertrans/translation/pipeline.py`
- Modify: `src/papertrans/translation/__init__.py`
- Modify: `tests/test_translation_reliability.py`

**Interfaces:**
- Produces: `TranslationUsage(input_tokens: int, cached_input_tokens: int, output_tokens: int, estimated_cost: float | None = None, currency: str | None = None, pricing_snapshot: str | None = None)`.
- Produces: `TranslationResult.usage: TranslationUsage | None`.
- Produces: `RetryableProviderError` and enhanced `NonRetryableProviderError`, each with `error_type`, `http_status`, and optional `usage`.
- Produces: `ProviderRunStats.add_usage(usage: TranslationUsage | None) -> None` and normalized billing fields in `to_dict()`.
- Consumes: existing `ReliableTranslationProvider.translate()` per-segment execution.

- [ ] **Step 1: Write failing usage and error-accounting tests**

Append focused cases to `tests/test_translation_reliability.py`:

```python
from papertrans.translation import (
    NonRetryableProviderError,
    TranslationUsage,
)


def test_fresh_usage_is_counted_but_cached_usage_is_not(tmp_path: Path) -> None:
    class UsageProvider(_CountingProvider):
        name = "usage"

        def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
            request = requests[0]
            self.calls.append(request.segment_id)
            return [
                TranslationResult(
                    segment_id=request.segment_id,
                    normal="译文",
                    provider=self.name,
                    usage=TranslationUsage(
                        input_tokens=100,
                        cached_input_tokens=25,
                        output_tokens=40,
                        estimated_cost=0.0012,
                        currency="USD",
                        pricing_snapshot="2026-07-31",
                    ),
                )
            ]

    cache_dir = tmp_path / "cache"
    first = ReliableTranslationProvider(UsageProvider(), cache_dir)
    first.translate([TranslationRequest(segment_id="s1", text="source")])
    assert first.stats.to_dict()["usage"] == {
        "input_tokens": 100,
        "cached_input_tokens": 25,
        "uncached_input_tokens": 75,
        "output_tokens": 40,
        "estimated_cost": 0.0012,
        "currency": "USD",
        "pricing_snapshot": "2026-07-31",
    }

    second = ReliableTranslationProvider(UsageProvider(), cache_dir)
    result = second.translate([TranslationRequest(segment_id="s1", text="source")])[0]
    assert result.usage is None
    assert second.stats.to_dict()["usage"]["input_tokens"] == 0
    assert second.stats.provider_calls == 0


def test_non_retryable_error_counts_usage_once_and_is_sanitized(tmp_path: Path) -> None:
    sentinel = "sk-sentinel-must-not-leak"

    class RejectedProvider:
        name = "rejected"

        def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
            raise NonRetryableProviderError(
                error_type="authentication_failed",
                http_status=401,
                usage=TranslationUsage(input_tokens=12, output_tokens=0),
            )

    reliable = ReliableTranslationProvider(RejectedProvider(), tmp_path / "cache")
    with pytest.raises(ProviderExecutionError) as exc_info:
        reliable.translate([TranslationRequest(segment_id="s1", text=sentinel)])
    assert exc_info.value.error_type == "authentication_failed"
    assert exc_info.value.http_status == 401
    assert sentinel not in str(exc_info.value)
    assert reliable.stats.to_dict()["usage"]["input_tokens"] == 12
    assert reliable.stats.retry_count == 0
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_reliability.py -v
```

Expected: FAIL because `TranslationUsage`, enhanced provider errors, usage aggregation, and sanitized error fields do not exist.

- [ ] **Step 3: Add the normalized usage value object**

Add to `src/papertrans/translation/base.py` and attach it to `TranslationResult`:

```python
@dataclass(frozen=True, slots=True)
class TranslationUsage:
    input_tokens: int
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None
    currency: str | None = None
    pricing_snapshot: str | None = None

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.cached_input_tokens, self.output_tokens) < 0:
            raise ValueError("Token usage cannot be negative")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("Cached input tokens cannot exceed input tokens")

    @property
    def uncached_input_tokens(self) -> int:
        return self.input_tokens - self.cached_input_tokens


@dataclass(frozen=True, slots=True)
class TranslationResult:
    segment_id: str
    normal: str
    compact: str | None = None
    provider: str = "unknown"
    usage: TranslationUsage | None = None
```

- [ ] **Step 4: Implement sanitized errors and fresh-call usage aggregation**

In `src/papertrans/translation/reliability.py`, give retryable and non-retryable errors the same sanitized shape, add usage totals to `ProviderRunStats`, call `add_usage()` for every completed API response or provider exception carrying usage, and never serialize usage into a translation cache entry:

```python
class ProviderError(RuntimeError):
    def __init__(
        self,
        *,
        error_type: str,
        http_status: int | None = None,
        usage: TranslationUsage | None = None,
    ) -> None:
        self.error_type = error_type
        self.http_status = http_status
        self.usage = usage
        super().__init__(error_type)


class RetryableProviderError(ProviderError):
    pass


class NonRetryableProviderError(ProviderError):
    pass
```

`ProviderExecutionError` must expose `error_type` and `http_status`, and its message must contain only segment ID, attempts, and error type. `ProviderRunStats.add_usage()` must reject mixed non-null currencies or snapshot dates rather than merge incompatible estimates.

When `_translate_one()` receives a successful result, add `result.usage`. When either provider error is caught, add `exc.usage` before retry or exit. `_write_cache()` continues to write only `normal`, `compact`, schema version, and provider. `_read_cache()` returns `usage=None`.

In `src/papertrans/translation/pipeline.py`, carry `result.usage` into the restored `TranslationResult` without using it for layout.

- [ ] **Step 5: Export the new interfaces and run focused tests GREEN**

Export `TranslationUsage`, `ProviderError`, and `RetryableProviderError` from `translation/__init__.py`, then run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_reliability.py tests/test_translation_protection.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/papertrans/translation/base.py src/papertrans/translation/reliability.py src/papertrans/translation/pipeline.py src/papertrans/translation/__init__.py tests/test_translation_reliability.py
git commit -m "feat: account for provider usage safely"
```

---

### Task 2: Provider Profiles, Pricing, and Versioned Academic Prompt

**Files:**
- Create: `src/papertrans/translation/profiles.py`
- Create: `src/papertrans/translation/prompt.py`
- Create: `tests/test_translation_profiles.py`

**Interfaces:**
- Consumes: `TranslationRequest` and `TranslationUsage` from Task 1.
- Produces: `ProviderPricing.estimate(usage: TranslationUsage) -> float`.
- Produces: `ProviderProfile.chat_url`, `ProviderProfile.request_overrides`, and `ProviderProfile.cache_identity(model: str) -> dict[str, object]`.
- Produces: `DEEPSEEK_PROFILE`, `KIMI_PROFILE`, and `compatible_profile(base_url: str, api_key_env: str) -> ProviderProfile`.
- Produces: `PROMPT_VERSION = "academic_pdf_zh_v1"` and `build_chat_messages(request: TranslationRequest) -> list[dict[str, str]]`.

- [ ] **Step 1: Write failing profile, price, and prompt tests**

Create `tests/test_translation_profiles.py`:

```python
import json

from papertrans.translation import TranslationRequest, TranslationUsage
from papertrans.translation.profiles import DEEPSEEK_PROFILE, KIMI_PROFILE
from papertrans.translation.prompt import PROMPT_VERSION, build_chat_messages


def test_named_profiles_use_current_official_defaults() -> None:
    assert DEEPSEEK_PROFILE.chat_url == "https://api.deepseek.com/chat/completions"
    assert DEEPSEEK_PROFILE.default_model == "deepseek-v4-flash"
    assert DEEPSEEK_PROFILE.api_key_env == "DEEPSEEK_API_KEY"
    assert DEEPSEEK_PROFILE.request_overrides == {"thinking": {"type": "disabled"}}
    assert KIMI_PROFILE.chat_url == "https://api.moonshot.cn/v1/chat/completions"
    assert KIMI_PROFILE.default_model == "kimi-k2.6"
    assert KIMI_PROFILE.api_key_env == "MOONSHOT_API_KEY"


def test_profiles_estimate_native_currency_cost() -> None:
    usage = TranslationUsage(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
    )
    assert DEEPSEEK_PROFILE.pricing is not None
    assert DEEPSEEK_PROFILE.pricing.estimate(usage) == 0.1337
    assert DEEPSEEK_PROFILE.pricing.currency == "USD"
    assert KIMI_PROFILE.pricing is not None
    assert KIMI_PROFILE.pricing.estimate(usage) == 7.85
    assert KIMI_PROFILE.pricing.currency == "CNY"


def test_prompt_is_versioned_and_carries_only_limited_segment_context() -> None:
    request = TranslationRequest(
        segment_id="flow-1",
        text="See ⟦PT0001⟧ in 10 ms.",
        protected_tokens=("⟦PT0001⟧", "⟦PT0002⟧"),
        context={"region_type": "paragraph"},
    )
    messages = build_chat_messages(request)
    payload = json.loads(messages[1]["content"])
    assert PROMPT_VERSION == "academic_pdf_zh_v1"
    assert [message["role"] for message in messages] == ["system", "user"]
    assert payload == {
        "source_language": "en",
        "target_language": "zh-CN",
        "region_type": "paragraph",
        "protected_tokens": ["⟦PT0001⟧", "⟦PT0002⟧"],
        "source_text": "See ⟦PT0001⟧ in 10 ms.",
    }
    assert "normal" in messages[0]["content"]
    assert "compact" in messages[0]["content"]
    assert "JSON" in messages[0]["content"]
```

- [ ] **Step 2: Run the new test and verify RED**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_profiles.py -v
```

Expected: FAIL because `profiles.py` and `prompt.py` do not exist.

- [ ] **Step 3: Implement exact profile and pricing types**

In `profiles.py`, define frozen dataclasses. Use `Decimal(str(rate))` internally and round the returned float to 12 decimal places:

```python
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
```

Use these reviewed snapshots:

```python
DEEPSEEK_PRICING = ProviderPricing(0.0028, 0.14, 0.28, "USD", "2026-07-31")
KIMI_PRICING = ProviderPricing(1.10, 6.50, 27.00, "CNY", "2026-07-31")
```

Review sources: `https://api-docs.deepseek.com/quick_start/pricing/` and
`https://platform.kimi.com/docs/pricing/chat-k26.md`.

`ProviderProfile.chat_url` must normalize one trailing slash and append `/chat/completions`. Its cache identity contains provider, normalized base URL, model, the profile thinking mode (`disabled` for named providers and `provider_default` for compatible), prompt version, and pricing snapshot, but never an environment value.

- [ ] **Step 4: Implement the versioned prompt builder**

In `prompt.py`, keep the system prompt constant so provider prefix caching can work. Serialize the user payload with `json.dumps(payload, ensure_ascii=False, sort_keys=True)` and include only the fields asserted by the test. The system prompt must require Simplified Chinese, semantic completeness, exactly-once unchanged placeholders, and the exact JSON object shape.

Use this fixed system prompt and builder shape:

```python
PROMPT_VERSION = "academic_pdf_zh_v1"
SYSTEM_PROMPT = (
    "Translate one protected academic-paper segment into Simplified Chinese. "
    "Preserve every listed placeholder exactly once and unchanged. Preserve all claims, "
    "citations, variables, units, and technical meaning. Return JSON only, with exactly two "
    "string fields: normal for the complete natural translation and compact for an equally "
    "complete but more concise layout candidate."
)


def build_chat_messages(request: TranslationRequest) -> list[dict[str, str]]:
    payload = {
        "source_language": request.source_language,
        "target_language": request.target_language,
        "region_type": request.context.get("region_type", "unknown"),
        "protected_tokens": list(request.protected_tokens),
        "source_text": request.text,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]
```

- [ ] **Step 5: Run focused tests GREEN**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_profiles.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/papertrans/translation/profiles.py src/papertrans/translation/prompt.py tests/test_translation_profiles.py
git commit -m "feat: define provider profiles and prompts"
```

---

### Task 3: Shared Chat Completions Client and Protection Precheck

**Files:**
- Modify: `pyproject.toml`
- Create: `src/papertrans/translation/compatible_client.py`
- Modify: `src/papertrans/translation/protection.py`
- Modify: `src/papertrans/translation/__init__.py`
- Create: `tests/test_translation_compatible.py`
- Modify: `tests/test_translation_protection.py`

**Interfaces:**
- Consumes: `ProviderProfile`, `TranslationRequest`, `TranslationResult`, `TranslationUsage`, provider errors, and `build_chat_messages()`.
- Produces: `placeholder_issues(text: str, expected: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]`.
- Produces: `ChatCompletionsTranslationProvider(profile, api_key, model, timeout_seconds, max_output_tokens, http_client)` implementing `TranslationProvider`.
- Produces: provider `cache_identity` without credentials.

- [ ] **Step 1: Write failing HTTP-contract and placeholder tests**

Create `tests/test_translation_compatible.py` with `httpx.MockTransport`. The success handler must inspect the request and return a DeepSeek-shaped response:

```python
import json

import httpx
import pytest

from papertrans.translation import (
    NonRetryableProviderError,
    RetryableProviderError,
    TranslationRequest,
)
from papertrans.translation.compatible_client import ChatCompletionsTranslationProvider
from papertrans.translation.profiles import DEEPSEEK_PROFILE


def test_client_posts_structured_non_thinking_request_and_parses_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {"content": json.dumps({
                        "normal": "中文⟦PT0001⟧",
                        "compact": "短文⟦PT0001⟧",
                    }, ensure_ascii=False)},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 100,
                    "prompt_cache_hit_tokens": 40,
                    "prompt_cache_miss_tokens": 60,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = ChatCompletionsTranslationProvider(
        profile=DEEPSEEK_PROFILE,
        api_key="sentinel-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
        max_output_tokens=800,
        http_client=client,
    )
    result = provider.translate([TranslationRequest(
        segment_id="s1",
        text="Source ⟦PT0001⟧",
        protected_tokens=("⟦PT0001⟧",),
    )])[0]
    assert captured["authorization"] == "Bearer sentinel-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["stream"] is False
    assert payload["max_tokens"] == 800
    assert result.normal == "中文⟦PT0001⟧"
    assert result.compact == "短文⟦PT0001⟧"
    assert result.usage is not None
    assert result.usage.cached_input_tokens == 40
    assert result.usage.uncached_input_tokens == 60
    assert result.usage.estimated_cost == 0.000014112


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_permanent_http_status_is_non_retryable(status: int) -> None:
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": {"message": "secret body"}})
    ))
    provider = ChatCompletionsTranslationProvider(
        DEEPSEEK_PROFILE, "sentinel-key", "deepseek-v4-flash", 30, 800, client
    )
    with pytest.raises(NonRetryableProviderError) as exc_info:
        provider.translate([TranslationRequest(segment_id="s1", text="source")])
    assert exc_info.value.http_status == status
    assert "secret body" not in str(exc_info.value)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_temporary_http_status_is_retryable(status: int) -> None:
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": {"message": "private"}})
    ))
    provider = ChatCompletionsTranslationProvider(
        DEEPSEEK_PROFILE, "sentinel-key", "deepseek-v4-flash", 30, 800, client
    )
    with pytest.raises(RetryableProviderError) as exc_info:
        provider.translate([TranslationRequest(segment_id="s1", text="source")])
    assert exc_info.value.http_status == status
    assert "private" not in str(exc_info.value)
```

Add a protection test asserting missing, duplicated, and unknown placeholder tuples from `placeholder_issues()`.

- [ ] **Step 2: Run the tests and verify RED**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_compatible.py tests/test_translation_protection.py -v
```

Expected: FAIL because the shared client and public placeholder analyzer do not exist.

- [ ] **Step 3: Add and install the bounded HTTP dependency**

Add to runtime dependencies in `pyproject.toml`:

```toml
"httpx>=0.28,<1",
```

Install the edited project:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

- [ ] **Step 4: Refactor placeholder analysis for reuse**

In `protection.py`, add `placeholder_issues()` using the existing `_PLACEHOLDER` regex. Refactor `restore_text()` to call it, preserving existing behavior and test output. The function returns expected placeholders missing from text, expected placeholders appearing more than once, and unknown placeholder syntax found in text.

- [ ] **Step 5: Implement the shared provider client**

`ChatCompletionsTranslationProvider.translate()` loops over requests and delegates each item to `_translate_one()`. `_translate_one()` must:

1. POST to `profile.chat_url` with bearer authentication and JSON body containing model, messages, `response_format={"type": "json_object"}`, `stream=False`, max tokens, and profile overrides.
2. Convert `httpx.TimeoutException` and `httpx.RequestError` into `RetryableProviderError(error_type="network_error")`.
3. Classify 400/401/402/403/404/422 as non-retryable, 408/429/5xx as retryable, and all other non-2xx statuses as non-retryable `provider_http_error`.
4. Parse usage before validating choices so malformed paid responses can carry usage into retry accounting.
5. Reject `finish_reason != "stop"`, missing choices, empty content, invalid JSON, non-string fields, empty strings, and placeholder issues with sanitized `RetryableProviderError` values.
6. Return one `TranslationResult` with the parsed `TranslationUsage` and provider name.

DeepSeek usage uses `prompt_cache_hit_tokens`; Kimi usage uses `cached_tokens`; compatible usage treats all prompt tokens as uncached when no cache field exists. Apply profile pricing to construct a second immutable `TranslationUsage` containing cost, currency, and snapshot.

`cache_identity` delegates to `profile.cache_identity(model)` and never includes `api_key`.

- [ ] **Step 6: Run focused tests GREEN**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_compatible.py tests/test_translation_protection.py tests/test_translation_reliability.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add pyproject.toml src/papertrans/translation/compatible_client.py src/papertrans/translation/protection.py src/papertrans/translation/__init__.py tests/test_translation_compatible.py tests/test_translation_protection.py
git commit -m "feat: add compatible chat translation client"
```

---

### Task 4: Named Adapters and Provider Registry

**Files:**
- Create: `src/papertrans/translation/deepseek.py`
- Create: `src/papertrans/translation/kimi.py`
- Create: `src/papertrans/translation/registry.py`
- Modify: `src/papertrans/translation/__init__.py`
- Create: `tests/test_translation_registry.py`

**Interfaces:**
- Consumes: shared client and provider profiles from Tasks 2 and 3.
- Produces: `DeepSeekTranslationProvider` and `KimiTranslationProvider` constructors with model override, timeout, max output tokens, and injected httpx client.
- Produces: `create_translation_provider(name: str, *, model: str | None = None, base_url: str | None = None, api_key_env: str | None = None, length_factor: float = 1.0, timeout_seconds: float = 60.0, max_output_tokens: int = 2048, environ: Mapping[str, str] | None = None, http_client: httpx.Client | None = None) -> TranslationProvider`.
- Produces: `PROVIDER_NAMES = ("mock", "deepseek", "kimi", "compatible")`.

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_translation_registry.py`:

```python
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
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(500)
    ))
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
```

- [ ] **Step 2: Run the registry tests and verify RED**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_registry.py -v
```

Expected: FAIL because named adapters and registry do not exist.

- [ ] **Step 3: Implement lightweight named adapters**

`DeepSeekTranslationProvider` and `KimiTranslationProvider` subclass `ChatCompletionsTranslationProvider` and pass only their fixed profile plus constructor arguments. They contain no HTTP parsing or retry logic.

```python
class DeepSeekTranslationProvider(ChatCompletionsTranslationProvider):
    def __init__(
        self,
        api_key: str,
        model: str = DEEPSEEK_PROFILE.default_model,
        timeout_seconds: float = 60.0,
        max_output_tokens: int = 2048,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            DEEPSEEK_PROFILE,
            api_key,
            model,
            timeout_seconds,
            max_output_tokens,
            http_client,
        )
```

Implement Kimi with the identical signature and `KIMI_PROFILE`.

- [ ] **Step 4: Implement registry validation and creation**

Normalize the provider name to lowercase and reject unknown values. For named providers, use only the fixed environment-variable names and reject `base_url` or `api_key_env`. For compatible, validate an absolute `http` or `https` URL with a host, require a model, and use the named environment variable or `PAPERTRANS_COMPATIBLE_API_KEY`. Never include an environment value in a raised message.

Use `compatible_profile()` and `ChatCompletionsTranslationProvider` for custom endpoints. Use `MockTranslationProvider` without inspecting credentials.

- [ ] **Step 5: Export adapters and registry, then run GREEN**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_registry.py tests/test_translation_compatible.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add src/papertrans/translation/deepseek.py src/papertrans/translation/kimi.py src/papertrans/translation/registry.py src/papertrans/translation/__init__.py tests/test_translation_registry.py
git commit -m "feat: register deepseek kimi and compatible providers"
```

---

### Task 5: Provider-Neutral Translation Job Runner

**Files:**
- Create: `src/papertrans/translation_job.py`
- Modify: `src/papertrans/mock_translation.py`
- Create: `tests/test_translation_job.py`
- Modify: `tests/test_mock_translation_pipeline.py`

**Interfaces:**
- Consumes: any `TranslationProvider`, existing reliability wrapper, extraction, protection, layout, rendering, and QA.
- Produces: `TranslationJobResult` with output and artifact paths plus report.
- Produces: `run_translation_job(source, output_dir, provider, *, cache_dir=None, max_attempts=3, requests_per_second=0.0) -> TranslationJobResult`.
- Preserves: `run_mock_translation()` as a compatibility wrapper.

- [ ] **Step 1: Write failing generic-runner tests**

Create `tests/test_translation_job.py` by moving the existing synthetic fixture shape into the test and use a counting deterministic provider:

```python
from pathlib import Path

import pymupdf

from papertrans.translation import TranslationRequest, TranslationResult
from papertrans.translation_job import run_translation_job


class DeterministicProvider:
    name = "deterministic"
    cache_identity = {"provider": "deterministic", "version": "v1"}

    def __init__(self) -> None:
        self.calls: list[str] = []

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        request = requests[0]
        self.calls.append(request.segment_id)
        suffix = "".join(request.protected_tokens)
        return [TranslationResult(
            segment_id=request.segment_id,
            normal=f"这是正常中文译文{suffix}",
            compact=f"紧凑译文{suffix}",
            provider=self.name,
        )]


def test_generic_job_writes_provider_neutral_artifacts_and_resumes(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_textbox(
        pymupdf.Rect(40, 80, 380, 260),
        "A paper paragraph cites https://example.org and finishes in 10 ms.",
        fontsize=9,
    )
    document.save(source)
    document.close()
    cache_dir = tmp_path / "cache"

    first_provider = DeterministicProvider()
    first = run_translation_job(
        source, tmp_path / "first", first_provider, cache_dir=cache_dir
    )
    assert first.output_pdf.is_file()
    assert first.report_json.name == "translation-report.json"
    assert first.report["provider"] == "deterministic"
    assert first.report["gates"]["provider_execution_completed"] is True
    assert first_provider.calls

    second_provider = DeterministicProvider()
    second = run_translation_job(
        source, tmp_path / "second", second_provider, cache_dir=cache_dir
    )
    assert second_provider.calls == []
    assert second.report["provider_execution"]["cache_hits"] > 0
    assert second.report["provider_execution"]["usage"]["input_tokens"] == 0
```

Add an assertion to `tests/test_mock_translation_pipeline.py` that the wrapper report provider remains `mock` and output remains valid.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_job.py tests/test_mock_translation_pipeline.py -v
```

Expected: FAIL because `translation_job.py` does not exist.

- [ ] **Step 3: Extract the provider-neutral runner**

Move artifact writers and the full extraction-to-QA flow from `mock_translation.py` into `translation_job.py`. Rename the result dataclass and report to generic names:

```python
@dataclass(frozen=True, slots=True)
class TranslationJobResult:
    output_dir: Path
    output_pdf: Path
    protected_segments_json: Path
    provider_run_json: Path
    translations_json: Path
    layout_json: Path
    report_json: Path
    report: dict[str, Any]
```

The temporary PDF suffix becomes `.translation.tmp.pdf`, the report filename becomes `translation-report.json`, and report mode becomes `translated_pdf`. Provider configuration in `provider-run.json` comes only from `cache_identity`; recursively reject secret-bearing field names such as `api_key`, `authorization`, `secret`, and `credential` before writing it. Do not reject legitimate accounting names such as `input_tokens` or `max_output_tokens`.

Keep `provider-run.json` state transitions `prepared -> completed` or `prepared -> failed`. On failure include only segment ID, attempts, `error_type`, and HTTP status. Preserve atomic cache behavior and all existing layout/PDF gates.

- [ ] **Step 4: Replace mock runner with a compatibility wrapper**

`run_mock_translation()` creates `MockTranslationProvider(length_factor)` and delegates to `run_translation_job()`. Alias `MockTranslationResult = TranslationJobResult` so existing imports continue working. Mock-only synthetic limitations remain in the report when `provider.name == "mock"`; external providers receive an external-transmission limitation string naming the selected provider.

- [ ] **Step 5: Run generic and legacy pipeline tests GREEN**

```powershell
.\.venv\Scripts\python -m pytest tests/test_translation_job.py tests/test_mock_translation_pipeline.py tests/test_roundtrip.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/papertrans/translation_job.py src/papertrans/mock_translation.py tests/test_translation_job.py tests/test_mock_translation_pipeline.py
git commit -m "refactor: generalize the translation job runner"
```

---

### Task 6: CLI Provider Selection and Argument Safety

**Files:**
- Modify: `src/papertrans/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `PROVIDER_NAMES`, `create_translation_provider()`, and `run_translation_job()`.
- Produces: documented translate arguments for provider, model, compatible base URL and key environment name, timeout, and max output tokens.
- Preserves: mock default and existing inspection/roundtrip behavior.

- [ ] **Step 1: Write failing parser and dispatch tests**

Create `tests/test_cli.py`:

```python
from pathlib import Path

import pytest

from papertrans.cli import build_parser


def test_translate_defaults_to_mock_without_api_key_argument() -> None:
    parser = build_parser()
    args = parser.parse_args(["translate", "paper.pdf"])
    assert args.provider == "mock"
    assert args.model is None
    assert args.base_url is None
    assert args.api_key_env is None
    option_strings = {
        option
        for action in parser._subparsers._group_actions[0].choices["translate"]._actions
        for option in action.option_strings
    }
    assert "--api-key" not in option_strings


def test_translate_accepts_named_and_compatible_configuration() -> None:
    parser = build_parser()
    deepseek = parser.parse_args([
        "translate", "paper.pdf", "--provider", "deepseek",
        "--model", "deepseek-v4-flash", "--timeout", "45",
        "--max-output-tokens", "1200",
    ])
    assert deepseek.provider == "deepseek"
    assert deepseek.timeout == 45
    assert deepseek.max_output_tokens == 1200
    compatible = parser.parse_args([
        "translate", "paper.pdf", "--provider", "compatible",
        "--base-url", "https://relay.test/v1", "--model", "cheap-model",
        "--api-key-env", "RELAY_API_KEY",
    ])
    assert compatible.base_url == "https://relay.test/v1"
    assert compatible.api_key_env == "RELAY_API_KEY"


def test_parser_rejects_unknown_provider() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "translate", str(Path("paper.pdf")), "--provider", "unknown"
        ])
```

Add this dispatch test using `monkeypatch`:

```python
from types import SimpleNamespace

from papertrans.cli import main


def test_main_dispatches_selected_provider_to_generic_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    provider_marker = object()
    output = tmp_path / "output"

    def fake_create(name: str, **kwargs: object) -> object:
        captured["name"] = name
        captured["settings"] = kwargs
        return provider_marker

    def fake_run(source: Path, output_dir: Path, provider: object, **kwargs: object) -> object:
        captured["provider"] = provider
        captured["output_dir"] = output_dir
        return SimpleNamespace(
            output_dir=output,
            output_pdf=output / "output.pdf",
            protected_segments_json=output / "protected-segments.json",
            provider_run_json=output / "provider-run.json",
            translations_json=output / "translations.json",
            layout_json=output / "layout.json",
            report_json=output / "translation-report.json",
            report={"passed": True},
        )

    monkeypatch.setattr("papertrans.cli.create_translation_provider", fake_create)
    monkeypatch.setattr("papertrans.cli.run_translation_job", fake_run)
    main([
        "translate",
        str(tmp_path / "paper.pdf"),
        "--provider",
        "kimi",
        "--output-dir",
        str(output),
    ])
    assert captured["name"] == "kimi"
    assert captured["provider"] is provider_marker
    assert captured["output_dir"] == output
    assert "Quality gate:       PASS" in capsys.readouterr().out
```

- [ ] **Step 2: Run CLI tests and verify RED**

```powershell
.\.venv\Scripts\python -m pytest tests/test_cli.py -v
```

Expected: FAIL because only `mock` is accepted and the new options are absent.

- [ ] **Step 3: Add CLI arguments and generic dispatch**

Set choices from `PROVIDER_NAMES`. Add:

```python
translate_parser.add_argument("--model")
translate_parser.add_argument("--base-url")
translate_parser.add_argument("--api-key-env")
translate_parser.add_argument("--timeout", type=float, default=60.0)
translate_parser.add_argument("--max-output-tokens", type=int, default=2048)
```

In the translate branch, call `create_translation_provider()` with parsed settings and then `run_translation_job()`. Keep `run_mock_translation()` out of the CLI path. Use output operation `f"{args.provider}-translation"`. Print `Translation complete`, selected provider, output PDF, manifests, layout, report, and gate status. Catch only sanitized `FileNotFoundError`, `ValueError`, and `RuntimeError` messages.

- [ ] **Step 4: Run CLI and existing command tests GREEN**

```powershell
.\.venv\Scripts\python -m pytest tests/test_cli.py tests/test_inspect.py tests/test_roundtrip.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```powershell
git add src/papertrans/cli.py tests/test_cli.py
git commit -m "feat: select translation providers from the cli"
```

---

### Task 7: Mock-HTTP PDF Integration, Security Gate, Documentation, and Milestone

**Files:**
- Create: `tests/test_provider_translation_pipeline.py`
- Modify: `README.md`
- Modify: `docs/BUILD_FLOW.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: all M4.3 interfaces from Tasks 1-6.
- Produces: deterministic full-PDF evidence for DeepSeek- and Kimi-shaped responses.
- Produces: user documentation for environment-only credentials and compatible-provider limitations.
- Changes milestone only after every test and PDF gate passes.

- [ ] **Step 1: Write the failing full-pipeline security test**

Create `tests/test_provider_translation_pipeline.py`. Parametrize DeepSeek and Kimi profiles. The mock HTTP handler must parse the user message JSON, preserve every listed placeholder exactly once, and return provider-specific usage fields:

```python
import json
from pathlib import Path

import httpx
import pymupdf
import pytest

from papertrans.translation import create_translation_provider
from papertrans.translation_job import run_translation_job


@pytest.mark.parametrize(
    ("provider_name", "key_env", "usage"),
    [
        ("deepseek", "DEEPSEEK_API_KEY", {
            "prompt_tokens": 100,
            "prompt_cache_hit_tokens": 20,
            "prompt_cache_miss_tokens": 80,
            "completion_tokens": 30,
            "total_tokens": 130,
        }),
        ("kimi", "MOONSHOT_API_KEY", {
            "prompt_tokens": 100,
            "cached_tokens": 20,
            "completion_tokens": 30,
            "total_tokens": 130,
        }),
    ],
)
def test_named_provider_pipeline_preserves_pdf_and_never_persists_key(
    tmp_path: Path,
    provider_name: str,
    key_env: str,
    usage: dict[str, int],
) -> None:
    sentinel = f"sk-{provider_name}-sentinel-never-write"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        user_payload = json.loads(body["messages"][1]["content"])
        tokens = "".join(user_payload["protected_tokens"])
        content = json.dumps({
            "normal": f"这是完整的论文中文译文{tokens}",
            "compact": f"论文紧凑译文{tokens}",
        }, ensure_ascii=False)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": usage,
        })

    source = create_provider_pdf_fixture(tmp_path / "source.pdf")
    cache_dir = tmp_path / "cache"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = create_translation_provider(
        provider_name,
        environ={key_env: sentinel},
        http_client=client,
    )
    first = run_translation_job(
        source, tmp_path / "first", provider, cache_dir=cache_dir
    )
    assert first.report["passed"] is True
    assert first.report["protection"]["passed"] is True
    assert first.report["layout"]["translated_line_overlap_count"] == 0
    assert first.report["layout"]["protected_region_overlap_count"] == 0
    assert calls > 0

    searchable = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (tmp_path / "first", cache_dir)
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".txt"}
    )
    assert sentinel not in searchable
```

Define `create_provider_pdf_fixture()` in the same test file with a two-column, white-background PDF containing a citation, URL, and unit:

```python
def create_provider_pdf_fixture(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_text((40, 55), "Provider Translation Test", fontsize=16, fontname="tibo")
    page.insert_textbox(
        pymupdf.Rect(40, 85, 190, 330),
        "This paper paragraph cites [1] and https://example.org/model. "
        "The measured latency is 10 ms and the method preserves layout.",
        fontsize=9,
        fontname="tiro",
    )
    page.insert_textbox(
        pymupdf.Rect(230, 85, 380, 330),
        "A second column verifies reading order, compact translation, and page geometry.",
        fontsize=9,
        fontname="tiro",
    )
    document.save(path)
    document.close()
    return path
```

- [ ] **Step 2: Run the full pipeline acceptance test**

```powershell
.\.venv\Scripts\python -m pytest tests/test_provider_translation_pipeline.py -v
```

Expected: PASS for both DeepSeek- and Kimi-shaped responses. If it fails, stop this task and use `superpowers:systematic-debugging` before changing production code; do not weaken the assertions.

- [ ] **Step 3: Run the entire deterministic suite and Ruff**

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 4: Run the mock-backed PDF quality gate**

Use a paper from `test_pdf/` and a fresh output directory without any external key:

```powershell
$paper = Get-ChildItem -LiteralPath .\test_pdf -Filter *.pdf | Select-Object -First 1
.\.venv\Scripts\papertrans translate $paper.FullName --provider mock --output-dir .\.papertrans\m4.3-mock-verification
```

Expected: CLI prints `Quality gate: PASS`; output contains `output.pdf`, `document.json`, `protected-segments.json`, `provider-run.json`, `translations.json`, `layout.json`, and `translation-report.json`.

- [ ] **Step 5: Document provider use and mark M4.3 complete**

Update `README.md` with exact environment and command examples:

```powershell
$env:DEEPSEEK_API_KEY = "set-locally"
.\.venv\Scripts\papertrans translate .\paper.pdf --provider deepseek

$env:MOONSHOT_API_KEY = "set-locally"
.\.venv\Scripts\papertrans translate .\paper.pdf --provider kimi

$env:MY_PROVIDER_API_KEY = "set-locally"
.\.venv\Scripts\papertrans translate .\paper.pdf --provider compatible `
  --base-url https://example.com/v1 `
  --model example-model `
  --api-key-env MY_PROVIDER_API_KEY
```

State that external providers receive protected paper segments, compatible mode is best-effort, prices are dated estimates, no automatic failover occurs, and mock remains offline/default. Document an optional live smoke procedure using a short non-sensitive synthetic PDF and a newly configured local key; never embed a key in the command or documentation.

Update `docs/BUILD_FLOW.md` and `AGENTS.md` together: mark M4.3 complete, summarize provider, usage, cost, and safety gates, and name the next milestone. Do not bring OCR, model downloads, or GUI work into scope.

- [ ] **Step 6: Re-run final verification after documentation changes**

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

Expected: all tests PASS and Ruff exits 0.

- [ ] **Step 7: Commit Task 7**

```powershell
git add tests/test_provider_translation_pipeline.py README.md docs/BUILD_FLOW.md AGENTS.md
git commit -m "docs: complete the multi-provider milestone"
```

---

## Final Review Checklist

- [ ] `mock` is the default and makes no external request.
- [ ] `deepseek`, `kimi`, and `compatible` require explicit selection.
- [ ] Named defaults are `deepseek-v4-flash` and `kimi-k2.6`, with non-thinking settings.
- [ ] `compatible` requires base URL and model and is labeled best-effort.
- [ ] There is no API-key CLI argument and no credential value in cache identity or artifacts.
- [ ] Normal and compact translations arrive from one JSON response.
- [ ] Placeholder precheck failures retry; final protection failures block rendering.
- [ ] Permanent HTTP failures do not retry; timeouts, 408, 429, and 5xx do retry.
- [ ] Fresh-call usage and dated price estimates are normalized; local cache hits bill zero.
- [ ] Partial failures preserve earlier atomic cache entries.
- [ ] DeepSeek- and Kimi-shaped full PDF tests pass without overlap or protected-region collision.
- [ ] No automatic provider failover, whole-PDF upload, OCR, model download, or GUI work was added.
- [ ] README, BUILD_FLOW, and AGENTS milestone state agree.
- [ ] Full pytest and Ruff verification pass after the final change.

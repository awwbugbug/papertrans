# M4.3 Multi-Provider Translation Design

Date: 2026-07-31
Status: Approved design, pending implementation plan

## 1. Context

PaperTrans has completed the M4.2 provider-neutral reliability baseline. Translation requests can
already pass through protected-segment validation, atomic disk caching, retry, rate limiting, and
resumability before translated text enters layout and PDF rendering.

M4.3 will add real external translation providers without coupling PDF processing to one vendor.
The first supported external providers are DeepSeek and Kimi. An advanced compatible-provider
entry point will allow users to connect other services that implement a sufficiently compatible
Chat Completions API.

## 2. Goals

- Let users explicitly select `mock`, `deepseek`, `kimi`, or `compatible` from the CLI.
- Share HTTP, authentication, timeout, request serialization, and common response parsing where
  vendor protocols overlap.
- Keep vendor-specific model settings, usage fields, pricing, and error behavior isolated.
- Return normal and compact Chinese translations in one structured response per source segment.
- Reuse the M4.2 protection, cache, retry, rate-limit, resumability, layout, render, and QA layers.
- Record normalized token usage and an auditable cost estimate without storing credentials or full
  paper text in provider diagnostics.
- Keep all tests deterministic and free of paid network calls by default.

## 3. Non-goals

- No automatic provider failover. Paper content must never be sent to another vendor without an
  explicit user choice.
- No OCR, GUI, model downloads, translation batch API, or whole-document upload.
- No guarantee that every nominally OpenAI-compatible third-party endpoint works.
- No automatic model discovery in the translation command.
- No chapter glossary, adjacent-paragraph context expansion, or cross-segment batching in M4.3.
- No exact billing guarantee. Reported costs are estimates based on provider usage fields and a
  dated pricing snapshot.

## 4. Chosen Architecture

The implementation uses a shared compatible protocol layer plus vendor-specific provider profiles
and adapters.

```text
CLI
  -> ProviderRegistry
      -> MockTranslationProvider
      -> DeepSeekTranslationProvider --+
      -> KimiTranslationProvider -------+-> ChatCompletionsClient
      -> CompatibleTranslationProvider -+
  -> ReliableTranslationProvider
  -> protected-token restoration and final validation
  -> CJK layout
  -> PDF rendering
  -> quality gates
```

The existing `TranslationProvider` boundary remains provider-independent. Provider code must not
import PDF, layout, or rendering modules. The shared HTTP client must not know how translated text
is placed on a page.

The current mock-only job runner will be refactored into a provider-neutral translation job runner.
Mock translation will use the same runner as external providers so there is only one artifact,
layout, render, and QA path.

Planned translation modules:

```text
translation/
|-- base.py
|-- registry.py
|-- profiles.py
|-- prompt.py
|-- compatible_client.py
|-- deepseek.py
|-- kimi.py
|-- mock.py
|-- protection.py
|-- pipeline.py
`-- reliability.py
```

## 5. Provider Profiles

Each named provider profile defines:

- provider name;
- official base URL;
- default model;
- API-key environment variable name;
- request extensions, including how thinking mode is disabled;
- structured-output capability;
- usage-field mapping;
- HTTP error classification;
- dated native-currency pricing snapshot;
- cache identity fields.

Initial profiles:

| Provider | Base URL | Default model | Key environment variable |
| --- | --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-v4-flash` | `DEEPSEEK_API_KEY` |
| Kimi | `https://api.moonshot.cn/v1` | `kimi-k2.6` | `MOONSHOT_API_KEY` |
| Compatible | User supplied | User supplied | `PAPERTRANS_COMPATIBLE_API_KEY` by default |

Translation uses non-thinking mode where the selected model supports it. The defaults favor low
cost, predictable latency, and structured translation rather than reasoning-heavy output. A user
may override the named provider's model, but the provider adapter still applies the translation
profile's non-thinking request settings when supported.

`compatible` is an advanced, best-effort option. It uses the common Chat Completions request and
response subset. Vendor-specific extensions, unusual authentication, and incompatible streaming
formats are outside its contract.

## 6. CLI and Configuration

External transmission must be explicit. `mock` remains the default provider.

```powershell
papertrans translate paper.pdf --provider deepseek
papertrans translate paper.pdf --provider kimi
papertrans translate paper.pdf --provider compatible `
  --base-url https://example.com/v1 `
  --model example-model `
  --api-key-env MY_PROVIDER_API_KEY
```

M4.3 CLI options:

- `--provider {mock,deepseek,kimi,compatible}`;
- `--model` to override a named default or supply the compatible model;
- `--base-url`, valid only for `compatible`;
- `--api-key-env`, valid only for `compatible`;
- `--timeout`;
- `--max-output-tokens`;
- existing `--cache-dir`, `--max-attempts`, and `--requests-per-second` options;
- existing `--length-factor`, valid only for `mock`.

There is deliberately no `--api-key` argument. API keys are read only from environment variables.
Missing credentials, model names, or compatible base URLs fail validation before any provider
request. Error messages may name the missing environment variable but must never show its value.

## 7. Request and Response Contract

The provider-independent prompt builder creates a versioned system prompt and a user payload from
one protected `TextFlow`. It includes:

- source and target languages;
- region type;
- protected source text;
- the exact placeholder list;
- instructions to preserve every placeholder exactly once and unchanged;
- an explicit JSON object example containing `normal` and `compact` strings.

The common request uses the non-streaming Chat Completions endpoint and requests JSON object output.
JSON object mode is the common denominator supported by the two initial providers. The provider is
asked to return:

```json
{
  "normal": "Normal-length Simplified Chinese translation",
  "compact": "More concise Simplified Chinese translation"
}
```

Both variants must preserve meaning. `compact` may remove redundancy but must not omit claims,
citations, units, variables, or other protected content. One provider request generates both
variants to avoid paying for two requests and to keep the candidates semantically aligned.

The client rejects empty content, malformed JSON, missing or non-string fields, truncated output,
and invalid choice structure. It performs an immediate placeholder-count precheck so malformed
provider output can enter the retry layer. The existing protection pipeline remains the final
authority before layout.

## 8. Job Data Flow and Artifacts

1. Parse and validate provider configuration.
2. Create the output directory and persist a sanitized prepared provider-run manifest.
3. Extract the source PDF into the Document IR.
4. Protect translatable flows and persist `protected-segments.json` before provider calls.
5. Build one versioned structured translation request per segment.
6. Check the local cache using the full provider configuration identity.
7. On a cache miss, call the provider through retry and rate limiting.
8. Precheck the response, then atomically cache each successful segment.
9. Restore and finally validate every protected token.
10. Persist translations, build layout, render the PDF, and run quality gates.
11. Finalize provider usage, cost estimate, and job status in `provider-run.json`.

The job remains segment-atomic. A failure on a later segment does not invalidate earlier cache
writes. Rerunning with identical input and provider configuration resumes from those entries.

Provider cache identity includes provider name, normalized base URL, model, thinking mode, prompt
version, source and target languages, protected request text, placeholder list, and request context.
It never contains a key or secret. Changing a key alone does not invalidate valid translation
cache entries; changing the endpoint, model, prompt, or translation inputs does.

## 9. Error Handling

Errors are classified before entering the reliability wrapper:

- Non-retryable: missing configuration, invalid base URL, authentication failure, insufficient
  balance, unsupported or missing model, and invalid request parameters.
- Retryable: connection failure, timeout, HTTP 408, HTTP 429, provider 5xx responses, empty JSON
  content, malformed structured output, output truncation, and placeholder precheck failure.

After retry exhaustion, the job records only a sanitized summary containing the segment ID, error
type, HTTP status when available, and attempt count. It must not persist request text, provider
response bodies, authorization headers, or API keys.

No PDF is rendered from an incomplete or protection-invalid translation set. Existing successful
segments remain in the atomic local cache for a later resume.

## 10. Usage and Cost Reporting

Fresh provider calls accumulate a normalized usage model:

```json
{
  "provider_calls": 36,
  "input_tokens": 18400,
  "cached_input_tokens": 7200,
  "uncached_input_tokens": 11200,
  "output_tokens": 9600,
  "estimated_cost": 0.004256,
  "currency": "USD",
  "pricing_snapshot": "2026-07-31"
}
```

DeepSeek's prompt cache hit and miss fields map directly to cached and uncached input. Kimi's
`cached_tokens` is subtracted from total prompt tokens to obtain uncached input. Negative or
internally inconsistent usage values are rejected rather than silently corrected.

Local PaperTrans cache hits contribute zero billable tokens to the current run. Historical API
usage is not charged again or copied into the current run total.

Named-provider profiles carry reviewed price snapshots in the provider's billing currency. The
report labels the result as an estimate and records the snapshot date and per-token rates used.
When a compatible provider does not expose adequate usage or known rates, unavailable fields and
estimated cost are `null`; PaperTrans must not invent them.

## 11. Security and Privacy

- API keys are read only from environment variables and remain outside artifacts, cache keys,
  exceptions, and logs.
- External providers receive only one protected text segment and limited structural context per
  request, not an uploaded whole PDF.
- The CLI and report identify the selected external provider before transmission.
- There is no automatic provider switching.
- Logs do not print complete source or translated paper paragraphs by default.
- Tests scan generated artifacts and sanitized exceptions to ensure a sentinel test key is absent.

## 12. Testing Strategy

### Provider unit tests

Use an injected mock HTTP transport. Verify endpoint construction, bearer authentication, model
selection, non-thinking settings, JSON request shape, response parsing, finish reason handling,
usage mapping, and cache identity. Unit tests never call a live provider.

### Error and security tests

Verify that authentication, balance, model, and parameter errors do not retry; rate limiting,
timeouts, network failures, 5xx responses, malformed JSON, truncation, and placeholder damage do
retry. Verify that no test key appears in artifacts, cache payloads, errors, or captured output.

### Pipeline integration tests

Use deterministic DeepSeek-shaped and Kimi-shaped responses to run protection, translation,
atomic cache, layout, rendering, and PDF QA against a synthetic academic PDF. Verify a second run
uses only local cache and reports zero fresh provider calls and zero fresh billable tokens.

### Optional live smoke tests

Live tests are excluded from pytest and require an explicit command plus a locally configured
environment variable. The first live check translates a short non-sensitive sample. A full user
paper is attempted only after the short request and protected-token validation succeed.

### Required verification

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

Provider implementation changes also require a mock-backed full translation job and PDF quality
gate. A user-authorized live smoke test is additional evidence, not a replacement for deterministic
tests.

## 13. Documentation and Milestone Update

When implementation and quality gates pass, update `README.md`, `docs/BUILD_FLOW.md`, and
`AGENTS.md` in the same change to mark M4.3 complete and record the exact supported providers,
configuration variables, limitations, and next milestone. Until then, the repository milestone
remains M4.2 complete and M4.3 in progress.

# AGENTS.md

This file defines repository-wide instructions for coding agents.

## Mission

Build a layout-aware academic PDF translator. Preserve content, formulas, figures, tables, links,
and visual hierarchy while minimizing layout distortion after translation.

## Required reading

Before changing pipeline behavior, read:

1. `README.md`
2. `docs/BUILD_FLOW.md`

Follow the milestone order in `docs/BUILD_FLOW.md`. Do not skip a quality gate to add a later-stage
feature.

## Current milestone

M5-C is complete: provider requests now receive deterministic, bounded section, neighbor, and
optional glossary context without weakening M4.3 protection or M5.1 fail-closed layout behavior.

- Native extraction, reading order, TextFlow recovery, and the `roundtrip` command are available.
- `translate --provider mock` supports CJK line breaking, cross-region flow, compact candidates,
  controlled font fallback, PDF rendering, and measurable quality gates.
- The four-paper normal-length baseline and a 1.3x long-text scenario pass without overflow or
  newly introduced sub-6pt text.
- `protected-segments.json` is persisted before provider execution. Citations, URLs, DOI values,
  explicit variables, and units must restore without missing, duplicate, or unknown placeholders.
- `provider-run.json` must be written before provider calls. Successful segments are cached
  atomically and must remain reusable after a later segment fails.
- Cache keys must include provider configuration identity but never API keys or secrets.
- `mock` remains the offline default. `deepseek`, `kimi`, and `compatible` require explicit user
  selection, and failures must never trigger automatic provider failover.
- DeepSeek defaults to `deepseek-v4-flash`; Kimi defaults to `kimi-k2.6`; named profiles use
  non-thinking requests. Compatible mode requires an explicit absolute HTTP(S) base URL and model
  and remains best-effort.
- Provider responses return normal and compact translations together. Fresh-call token usage and
  dated cost estimates are recorded; cache hits report zero new billable usage.
- Credentials are environment-only and must never enter cache identity, artifacts, diagnostics, or
  test fixtures. External providers receive protected segments and context, not the whole PDF.
- Deterministic DeepSeek- and Kimi-shaped full-PDF tests cover protected content, usage/cost,
  cache resume, secret persistence, layout collision gates, and successful rendering.
- Local repair deterministically tries normal and compact translations with controlled font
  fallback. M5.1 does not add Beam Search, conflict graphs, candidate caps, or an optimizer.
- `validate_layout()` independently rechecks flow selection, overflow, font floors, source
  bindings, page bounds, translated overlap, and protected-region overlap without persisting text
  in its diagnostics.
- Unsafe layouts enter REVIEW before rendering. A temporary PDF replaces `output.pdf` only after
  all existing PDF quality gates pass; failed runs preserve any previous output byte-for-byte.
- The four-paper normal baseline and Fast R-CNN 1.3x scenario pass with zero overflow, translated
  overlap, protected overlap, or newly introduced sub-6pt text.
- Context schema `m5c_v1` supplies at most a 200-character active heading and 600 characters from
  each immediate translatable neighbor. Distant paragraphs never enter the same request.
- `--glossary` accepts a validated UTF-8 JSON object with at most 500 entries and sends only terms
  present in the current segment. Glossary paths and full glossary content are not persisted in
  reports.
- Prompt version `academic_pdf_zh_v2` makes the current-segment boundary explicit. Context and
  relevant glossary entries participate in existing hash cache keys without entering cache
  metadata as plaintext.
- `translation-report.json` records aggregate context coverage and clipping counts only.
- A real-paper offline Mock run covers 117 contextualized flows and passes the existing PDF gates
  with zero overflow, translated overlap, and protected overlap.
- Whole-document prompts, vector retrieval, automatic terminology mining, and cross-segment
  provider batches remain deferred.
- The next planned milestone is M6 selective OCR for pages or regions without a reliable text
  layer. Do not download any OCR model before following the repository model download policy.

When the milestone changes, update this section and the build-flow status in the same change.

## Architecture boundaries

- `domain/` contains provider-independent document models.
- `ingest/` converts source formats into the Document IR.
- `translation/` contains provider interfaces and adapters only.
- `layout/` measures and solves translated layout.
- `render/` creates output documents.
- `inspect/` creates human-inspectable diagnostics.
- `qa/` owns automated quality metrics and regression gates.

Do not pass raw PyMuPDF objects across these boundaries. Convert them into domain models first.
Translation providers must not know how PDFs are rendered. Renderers must not call external
translation APIs.

`Region.source_text` preserves geometry-bound extraction text. Translation consumes normalized
`TextFlow.source_text`; every flow must retain stable `region_ids`, `page_numbers`, and diagnostic
metadata so translated text can be mapped back to its original boxes.

## Model download policy

Do not automatically download OCR, translation, vision-language, or embedding models.

If a model is required:

1. Stop before downloading it.
2. Give the user the model name, official project page, direct official download link, approximate
   size, official checksum when available, and expected local destination.
3. Continue only after the user confirms the local file is ready.

Models belong under `models/` and are never committed. Python package installation is allowed;
this restriction concerns large model weights and datasets.

## Engineering rules

- Support Python 3.11 or newer.
- Keep intermediate artifacts explicit, versioned, and JSON-serializable.
- Preserve stable IDs for pages, regions, and translation segments.
- Every heuristic must expose a confidence or a diagnostic marker.
- Never silently drop, clip, overlap, or mistranslate protected content.
- Prefer deterministic behavior and reproducible tests.
- Keep API keys in environment variables or ignored local configuration.
- Do not log complete paper text by default.

## Verification

Run before handing off code changes:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

For changes to PDF inspection, also run `papertrans inspect` on a fixture or user-provided PDF and
verify that `document.json`, page images, layout overlays, and the Markdown report are produced.

For reconstruction changes, run `papertrans roundtrip` and verify page count, dimensions, links,
skipped regions, text similarity, and visual error in `roundtrip-report.json`. Never pass a
roundtrip by copying the source unchanged; translatable spans must actually be removed and redrawn.

Every bug involving a PDF layout should gain a minimal regression fixture when licensing and file
size permit. Otherwise, record a reproducible synthetic fixture generator.

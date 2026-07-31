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

M4.2 is complete: provider-neutral cache, retry, rate limiting, and resumability are integrated.

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
- The next milestone is M4.3: add an OpenAI-compatible provider on top of the existing protection
  and reliability layers, including usage and cost reporting.
- OCR, model downloads, and GUI work remain out of scope until the M4 and M5 gates are stable.

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

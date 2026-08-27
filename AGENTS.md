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

M7.1 is complete: its stable feature baseline and Windows shell have been migrated from pywebview
to Tauri 2, and user acceptance of native window feel has passed. The React UI and token-protected
loopback FastAPI service remain; Tauri owns native file/directory selection and window behavior.
M7.2, M7.3, M7.4, and M7.5 are complete after user acceptance. The Windows 0.1.0 release is
frozen with a PyInstaller sidecar and NSIS installer without weakening M4.3 protection, M5.1
layout safety, M5-C bounded context, M6.4 mixed-page OCR arbitration, or the stable M7.4
continuous-reading baseline.

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
- CLI credentials remain environment-only. Desktop provider configurations are stored per provider
  in the current Windows user's Credential Manager, loaded into UI memory at startup, and passed
  through an ephemeral provider environment mapping. They must never enter browser storage, cache
  identity, Python artifacts, diagnostics, or test fixtures. External providers receive protected
  segments and context, not the whole PDF.
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
- Mixed-page OCR renders image crops rather than whole pages, maps recognition coordinates with
  the crop offset, removes lines that duplicate native text, and only fuses text-heavy regions.
- A text-heavy crop requires at least 3 accepted lines, 80 non-whitespace characters, and 0.80
  mean confidence. Sparse figure labels remain protected and do not become translation flows.
- `m6_ocr_plan_v3` adds `use_mixed`; `m6_ocr_run_v2` records candidate, accepted, and ignored
  regions plus duplicate-line counts without persisting paper text.
- The practical mixed-page PP-OCRv6 and mock-translation gate passes with zero overflow, new
  sub-6pt text, translated overlap, or protected overlap. Extreme phone-photo scans are not a
  current blocking quality gate.
- The M7.1 React/TypeScript UI runs in a Tauri 2 WebView2 shell over a token-protected loopback
  FastAPI child process. `mock` remains the default and the real PDF path uses
  `run_translation_job()`. Do not reintroduce pywebview, WinForms, or raw Win32 frame patches.
- Native Tauri compilation, launch, titlebar dragging, edge resizing, maximize/restore,
  drag-to-restore, Windows corner behavior, and no-black-border appearance have passed user
  acceptance. Explicit capability permissions cover custom minimize, maximize/restore, close, and
  dragging. M7.2 now has a token-protected `POST /api/text-translations` backend path that reuses
  provider selection, ephemeral credentials, protected tokens, reliable cache, and the isolated
  `standalone_text_zh_v1` prompt; it accepts at most 20,000 characters. The translation service and
  cache do not persist raw source text or credentials. After success, the local desktop library
  intentionally stores text source/translation files under `.papertrans/library/<task-id>/` so the
  user can restore them after restart; its atomic `m7_library_v1` index contains metadata only and
  never API keys. PDF jobs share the same index and retain status plus source/output paths. The
  warehouse lists both task types in separate columns, restores text tasks, restores completed PDF
  tasks to the dual reader, and opens PDF result folders. User acceptance has passed. M7.3 replaces
  browser-native PDF embeds with a lazy-loaded PDF.js canvas reader. Source and output readers keep
  separate page/zoom state with user-controlled synchronization, fit independently to their panels,
  and keep authenticated artifact URLs. Selectable text layers, authenticated paragraph geometry,
  cross-page linked highlighting, and Space-drag panning are complete. Packaged Python sidecar,
  installers, and dedicated table/formula OCR remain deferred.
- `translation-report.json` records aggregate context coverage and clipping counts only.
- A real-paper offline Mock run covers 117 contextualized flows and passes the existing PDF gates
  with zero overflow, translated overlap, and protected overlap.
- Whole-document prompts, vector retrieval, automatic terminology mining, and cross-segment
  provider batches remain deferred.
- `ocr-plan.json` uses schema `m6_ocr_plan_v3` and routes pages to `keep_native`, `run_ocr`,
  `use_ocr`, `use_mixed`, `review`, or `skip_blank`. Every decision includes confidence and reason
  codes.
- OCR is opt-in through `--ocr-backend paddleocr --ocr-model-dir <directory>`; the default path is
  model-free, and native pages must cause zero OCR calls.
- OCR Region and TextFlow metadata use `content_source=paddleocr` and retain engine confidence,
  mapped PDF geometry, and the original recognized polygon.
- `ocr-run.json` records only backend/device and aggregate page/line counts. It must never include
  paper text, secrets, or absolute model paths.
- PaddleOCR uses the local PP-OCRv6 medium detection and recognition directories. Do not enable
  MKL-DNN on the Windows CPU baseline because PaddlePaddle 3.3.1 fails in its oneDNN PIR bridge.
- Successful OCR pages become `use_ocr`; `run_ocr` and `review` remain fail-closed before provider
  execution. Existing output PDFs must remain byte-for-byte unchanged on failure.
- OCR paragraph recovery must use `ocr_same_paragraph` diagnostic edges and keep stable Region IDs.
  It may merge same-column lines but must not merge across a column boundary.
- `ocr-quality.json` uses schema `m6_ocr_quality_v1` and records only counts and metrics: CER, token
  order similarity, character coverage, dimensions, policy, and violations. It must not store text.
- The controlled ResNet page-2 raster baseline is CER 0.026003, token order 0.96702, coverage
  1.001282, 85 OCR line edges, and 10 final TextFlows. It is a reproducible proxy, not an authentic
  physical scan.
- The token-protected `m7_reading_map_v1` backend geometry contract and selectable PDF.js text
  layers are complete. Paragraph double-click PDF coordinates select one stable flow ID, which drives linked
  source/translation highlights without blocking selection or reducing the reader with content docks.
  Source-aware opposite-reader scrolling is complete and centers only off-screen targets while
  respecting reduced motion. Same-flow PDF.js word/phrase selection is complete, is mutually
  exclusive with paragraph navigation, remains local to the React session, and does not claim
  bilingual word alignment or automatically call a provider.
  Page and zoom synchronization can be independently disabled; explicit mapping still navigates to
  the corresponding page.
- Token-protected `POST /api/selection-translations` is the explicit selected-text backend
  contract. It accepts at most 300 characters, uses `selected_text_zh_v1` and `m7_selection_v1`,
  reuses protected tokens and reliable provider execution, and never creates a library task. The
  frontend calls it only after an explicit selection-adjacent source-reader action; automatic
  selection-triggered provider calls remain prohibited. The toolbar contains no selection summary
  or action. Loading, failure, and result use a nearby page-surface session overlay that does not
  reduce the reader height, and stale requests are aborted when selection context changes.
  PDF.js rendering is isolated from transient React callback identity, continuous resize events are
  debounced, and completed offscreen canvas/text-layer renders replace the visible page atomically.
  Desktop interaction acceptance has passed. M7.3 is closed.
- M7.4 must virtualize page surfaces around the viewport and release distant canvas/text-layer
  resources; never render every paper page at high resolution. The most-visible page drives toolbar
  state, per-page reading maps remain session-only, and programmatic navigation must not create
  observer feedback loops. Preserve selection, double-click mapping, Space-pan, atomic rendering,
  independent/synchronized readers, and explicit selected-text translation throughout the migration.
- The M7.4 stage-one baseline uses lightweight slots for every page and mounts `PdfPageSurface` only
  for the current page plus a radius of two (at most five canvas/text-layer pairs per reader).
  `IntersectionObserver` selects the most-visible page, while an explicit programmatic target
  suppresses intermediate observer updates. Stage two now maintains a cancellable session-only
  reading-map cache for the union of both readers' ±2 page windows (at most ten pages); each page
  becomes available independently, and stale windows are aborted and evicted. The next gate is
  synchronized continuous scrolling validation.
- Cross-page linked navigation converts surface bounds into scroll-container coordinates and holds
  its programmatic-navigation lock through both page travel and paragraph centering. Ctrl-wheel uses
  a cursor-anchored CSS preview and commits one PDF.js redraw only after 140 ms of input stability;
  zoom preview must not recreate the page observer or retrigger page navigation.
- Continuous page synchronization commits a most-visible page only after an 80 ms stable candidate
  window. Reversing at a page boundary replaces the candidate, and programmatic page/mapping
  navigation cancels it before scrolling. Sync-off readers remain independent, while explicit
  paragraph mapping still navigates. M7.4 passed desktop user acceptance and is closed.
- M7.5 proceeds in four ordered gates: preserve the translation workspace across navigation, add
  explicit API configuration dialogs, show bounded paper-title/text previews in the library, then
  add local history deletion and bounded cache/resource cleanup. Do not skip ahead between gates.
- The first M7.5 gate keeps the translation workspace mounted while library/settings are active.
  Hide it with `visibility` plus `inert`, never `display: none`, so PDF.js document instances,
  canvases, scroll positions, page/zoom state, and session reading maps survive navigation without
  leaving hidden controls focusable.
- The second M7.5 gate gives DeepSeek, Kimi, and compatible providers one controlled configuration
  dialog with separate credentials/model/base URL per provider. Tauri persists them only in Windows
  Credential Manager and reloads them into UI memory; they must not enter browser persistence or
  Python artifacts, and saving must not send a test request. Keep Escape/backdrop cancellation,
  keyboard focus containment, secret masking, and native password-reveal suppression.
- The third M7.5 gate passed user acceptance. PDF library rows use a bounded,
  normalized title extracted from first-page academic typography, with PDF metadata and filename-stem
  fallbacks; existing filename-only records are upgraded in place once. Text rows return only a
  normalized 120-character preview read from the dedicated local source file, while the full source
  remains outside `library.json`. Both row types use a single-line ellipsis and bounded tooltip.
- The fourth M7.5 gate passed user acceptance. History deletion requires an
  explicit confirmation and is blocked for running tasks. PDF deletion removes only the library
  record and retains both original and output files; text deletion atomically removes its index
  entry and app-owned `.papertrans/library/<task-id>/` content. Cache cleanup is scoped to
  `.papertrans/cache/`, is blocked while a translation runs, and never deletes tasks, originals, or
  outputs. Temporary-upload cleanup removes only unreferenced children of the app-owned uploads
  root. All recursive cleanup must stay under validated managed roots and never follow symlinks or
  Windows reparse points.
- The frozen Windows build launches a bundled `papertrans-backend` sidecar in release mode and
  stores tasks, cache, and uploads under `%LOCALAPPDATA%\com.papertrans.desktop`. Development mode
  keeps using the repository `.venv` and `.papertrans`. The standard installer bundles only the
  user-provided PP-OCRv6 medium detection and recognition directories after validating their
  inference files, and the release sidecar reads them from the immutable Tauri resource directory.
  The installer must never bundle repository history, API keys, test PDFs, or development caches.
- The Windows 0.1.1 packaging correction explicitly wires the same icon set into the application,
  tray, shortcuts, NSIS installer, and uninstaller. Release binaries use the Windows GUI subsystem.
  The packaged one-file sidecar is assigned to a kill-on-close Windows Job Object, and the official
  Tauri single-instance plugin restores the existing window before any second backend can start.
- The main window now closes to a Tauri-owned Windows tray by default. A left click or the explicit
  show menu item restores and focuses the existing window without remounting React/PDF.js; the tray
  quit item and the user-controlled `exit on close` setting perform a real app exit so the existing
  backend cleanup runs. Keep the Rust-side default fail-safe as close-to-tray, and do not implement
  tray behavior with a second window, a second backend, or frontend-only close interception.
- `GET /api/jobs/{job_id}/reading-map/{page_number}` returns stable TextFlow IDs, page dimensions,
  source Region boxes, and final translated LinePlacement boxes. It may return source/translation
  text to the authenticated local reader, but must never expose task paths, font paths, API keys,
  or provider diagnostics.

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

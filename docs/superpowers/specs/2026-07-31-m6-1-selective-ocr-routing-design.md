# M6.1 Selective OCR routing

## Goal

Add a deterministic, model-free preflight that decides whether each PDF page can keep its native
text layer, needs OCR, needs human review, or is safely blank. This milestone does not execute OCR
and does not download model weights.

## Page actions

- `keep_native`: preserve the native PDF text layer and continue normally.
- `run_ocr`: a scan-like raster page has no reliable native text; an OCR backend is required.
- `review`: the evidence is ambiguous or the extracted text looks unreliable.
- `skip_blank`: no text, raster image, or vector drawing was detected.

`run_ocr` and `review` are blocking actions for translation until a later OCR/fusion stage resolves
them. The translation provider must not be called for a blocked document.

## Deterministic evidence

The planner operates only on the provider-independent Document IR. For each page it records:

- non-whitespace native character count;
- native text-region count;
- suspicious native character ratio;
- union coverage of native raster-image regions;
- native vector-drawing count.

Initial fixed thresholds are 80 characters for a strong native layer, 12 characters for scan-like
sparse overlays, 0.85 minimum text-quality ratio, and 0.60 raster coverage for scan evidence.
Sparse but otherwise valid native text without scan evidence remains native, avoiding false OCR on
title or divider pages.

## Artifacts and provenance

- `inspect` writes `ocr-plan.json` with schema `m6_ocr_plan_v1`, policy thresholds, aggregate counts,
  and page decisions.
- Page decisions are copied into `Page.metadata.ocr` before `document.json` is serialized.
- Native text regions record `content_source=native_pdf` and `content_confidence=1.0`; TextFlow
  metadata summarizes its region sources.
- No page image, OCR model, paper text, or external request is added by this planner.

## Quality gates

- Existing born-digital paper pages remain `keep_native`.
- A full-page raster scan with no native text becomes `run_ocr`.
- A mixed raster/native page with ambiguous sparse text becomes `review`.
- A truly empty page becomes `skip_blank`; vector-only pages become `review`.
- Blocked translation writes inspectable `document.json` and `ocr-plan.json`, does not call the
  translation provider, and does not create or replace `output.pdf`.

## Deferred work

PaddleOCR execution, page rendering for OCR, OCR-region fusion, tables, formulas, language packs,
model selection, and model downloads are deferred until this routing gate passes real and synthetic
fixtures.

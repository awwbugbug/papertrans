# M6.2 Local OCR execution and IR fusion

## Goal

Run an explicitly configured local PaddleOCR backend only on pages routed to `run_ocr`, then fuse
recognized text geometry and confidence into the existing Document IR. Native-text pages must not
load or call the OCR model.

## User contract

- OCR remains disabled by default.
- `inspect` and `translate` accept `--ocr-backend paddleocr`, `--ocr-model-dir <path>`, and
  `--ocr-device cpu|gpu`.
- PaddleOCR requires complete local detection and recognition inference directories. Missing or
  ambiguous files fail before model initialization; the code never downloads weights.
- M6.2 initially supports CPU as the reproducible baseline. GPU is explicit and best-effort.

## Pipeline

1. Extract native PDF content and build the initial OCR plan.
2. Render only `run_ocr` pages at 200 DPI inside the ingest boundary.
3. Run the selected backend and convert pixel polygons to PDF point coordinates.
4. Add stable OCR Regions with `content_source=paddleocr`, engine confidence, model identity, and
   source image scale.
5. Mark a scan-like full-page raster as `ocr_background`; preserve it visually but exclude it from
   translated-text collision cutouts.
6. Re-run reading-order and TextFlow recovery, then build the final OCR plan.

The final plan schema is `m6_ocr_plan_v2`. A page with sufficient fused text and mean OCR confidence
of at least 0.80 becomes `use_ocr`; low-confidence or incomplete OCR remains `review`.

## Backend boundary

`OCRBackend` accepts a rendered page value object and returns immutable text-line values containing
text, a polygon, and confidence. The PaddleOCR import and model initialization are lazy so that
born-digital documents do not pay OCR startup cost. Tests use a deterministic fake backend.

## Artifacts and privacy

- `ocr-plan.json` contains the final page decisions and bounded diagnostics.
- `ocr-run.json` records backend identity, selected pages, line counts, confidence aggregates, and
  statuses, but not paper text or absolute model paths.
- OCR text and geometry appear in `document.json` because they are part of the Document IR.
- No model weight is copied into task artifacts or Git.

## Quality gates

- A born-digital paper produces zero OCR calls and remains byte-compatible with the existing flow.
- A synthetic image-only paper becomes `use_ocr`, has stable OCR Region and TextFlow provenance,
  and can pass the offline Mock translation pipeline.
- Low-confidence OCR enters REVIEW before provider calls.
- OCR coordinates stay inside page bounds and preserve reading order.
- Existing output PDFs remain unchanged on OCR or layout failure.
- Rendered OCR and translated-page PNGs receive visual inspection for overlap and legibility.

## Deferred work

Mixed-page `review` overrides, table reconstruction, formula OCR, handwriting tuning, orientation
and unwarping models, OCR result caching, GPU performance tuning, and region-level partial OCR are
deferred until page-level fusion is stable.

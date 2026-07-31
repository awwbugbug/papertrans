# M5.1 Layout Safety and Bounded Repair Design

**Date:** 2026-07-31
**Milestone:** M5.1, layout safety baseline

## Goal

Improve translated PDF safety without introducing a general optimization system before real
failure data proves one is needed. M5.1 keeps the original page count and uses the existing
deterministic CJK layout attempts. If the result cannot be proven safe, the job enters `REVIEW`
and does not create or replace `output.pdf`.

## Scope

M5.1 reuses the existing local repair order:

1. normal translation at the original font size;
2. compact translation at the original font size;
3. normal and compact translations at deterministic 0.5pt decrements;
4. stop at the existing 72% scale and 6pt readability floors.

Each `TextFlow` remains bound to its original `region_ids` and `page_numbers`. Occupied line slots
are skipped when they collide with formulas, figures, tables, or already placed translations.
No horizontal column movement, new page, or arbitrary region expansion is added.

M5.1 adds one independent validation pass after local layout and before rendering. It recomputes
violations from `Document` geometry and selected `LinePlacement` values instead of trusting layout
statistics.

## Hard safety checks

The validator returns fixed reason codes and aggregate counts only. It must not persist paper or
translation text. It checks:

- every translated flow has exactly one layout result;
- no flow reports overflow;
- no newly reduced text is below 6pt or 72% of its source size;
- every placement remains bound to an existing source region and page;
- placement boxes remain inside the original page;
- translated lines do not overlap other translated flows;
- translated lines do not overlap protected regions.

Possible reason codes are `missing_flow`, `duplicate_flow`, `unexpected_flow`, `overflow`,
`font_floor`, `region_binding`, `page_bounds`, `translated_overlap`, and `protected_overlap`.

## Job behavior

`layout.json` and a text-free safety report remain inspectable even when validation fails.

- Safe layout: render to a temporary PDF, run existing PDF quality gates, and atomically replace
  `output.pdf` only if all gates pass.
- Unsafe layout: skip rendering, write `translation-report.json` with `status: review`, keep
  provider cache and translation artifacts, and leave any previous `output.pdf` byte-for-byte
  unchanged.
- Rendered candidate failing PDF quality gates: delete the temporary candidate, report `REVIEW`,
  and preserve any previous output.

## Explicitly deferred

M5.1 does not add Beam Search, conflict graphs, page components, candidate caps, objective weights,
OR-Tools, a `--layout-beam-width` option, cross-column movement, or new-page creation. Those are
considered only after a recorded corpus demonstrates repeated failures that bounded local repair
cannot solve.

OCR, model downloads, GUI work, and translation-context expansion remain outside M5.1.

## Completion gate

M5.1 is complete when:

- unit tests cover every safety reason and text-free diagnostics;
- unsafe layouts never render or replace an output PDF;
- the existing full test suite and Ruff pass;
- the four-paper normal baseline and the existing 1.3x stress baseline remain free of overflow,
  translated overlap, protected overlap, and newly introduced sub-6pt text.

# M5.1 Layout Safety and Bounded Repair Implementation Plan

**Design:** `docs/superpowers/specs/2026-07-31-m5-1-global-layout-solver-design.md`

## 1. Remove speculative solver surface

- Restore `layout/models.py` to the existing `LinePlacement`, `FlowLayout`, and `DocumentLayout`
  models.
- Remove Beam Search configuration, candidate graph, cost, and search diagnostic models and their
  tests.
- Keep the existing CJK local attempt order and output schema compatible.

## 2. Extract geometry and add independent safety validation

- Add pure box helpers in `layout/constraints.py` and import them from `layout/cjk.py`.
- Add a text-free `LayoutSafetyReport` and `validate_layout()`.
- Cover flow selection, overflow, font floors, region/page binding, page bounds, translated
  collision, protected collision, and valid layouts with synthetic tests.

## 3. Make rendering fail closed

- Validate the selected layout before rendering.
- Render to a temporary PDF and replace the final output only after all existing PDF gates pass.
- On failure, write inspectable artifacts and a `REVIEW` report without creating or replacing the
  final PDF.
- Add a regression proving a previous output remains byte-for-byte unchanged after an unsafe run.

## 4. Verify the baseline

- Run focused layout and translation-job tests.
- Run the complete pytest suite and Ruff.
- Run the offline Mock provider on the paper baseline, including the 1.3x stress case.
- Update `README.md`, `docs/BUILD_FLOW.md`, and `AGENTS.md` only after the completion gates pass.

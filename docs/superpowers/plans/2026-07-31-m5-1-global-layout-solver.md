# M5.1 Deterministic Global Layout Solver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flow-order-dependent CJK placement with a deterministic page-level candidate solver that preserves page count, blocks incomplete PDF rendering, and emits inspectable solver diagnostics.

**Architecture:** Split layout into immutable models, pure candidate generation, independent constraints, deterministic page-component beam search, and a facade that produces either a validated `DocumentLayout` or a typed review result. Integrate the result into the provider-neutral translation job without changing provider cache identity or any M4.3 protection/reliability behavior.

**Tech Stack:** Python 3.11+, dataclasses, `hashlib`, `json`, existing PyMuPDF font metrics/rendering, pytest, Ruff. No new runtime dependency or model download.

## Global Constraints

- The approved specification is `docs/superpowers/specs/2026-07-31-m5-1-global-layout-solver-design.md`.
- Original page count, page membership, column membership, reading order, links, formulas, figures, tables, and protected tokens are immutable.
- A solved layout has zero overflow, zero translated-line overlap, zero protected-region overlap, font scale at least `0.72`, and font size at least `6pt`.
- A review result never creates or replaces `output.pdf`; a pre-existing valid PDF remains byte-for-byte unchanged.
- Normal translation at scale `>= 0.90` outranks compact translation at scale `>= 0.90`; below `0.90`, larger font wins before variant preference.
- Controlled whitespace borrowing is vertical only, stays in the original page/column, uses `2pt` steps, and caps each boundary at `min(12pt, region_height * 0.20)`.
- Default beam width is `64`; no automatic fallback to the legacy greedy algorithm is permitted.
- Solver diagnostics and error summaries contain IDs, geometry, counters, and fixed reason codes, not rejected full translation text or credentials.
- Provider requests, protected-token handling, atomic cache writes, usage/cost accounting, and zero-billing cache replay retain M4.3 semantics.
- OCR, model downloads, GUI, Google Translate, context/terminology enhancement, free page reflow, and OR-Tools remain out of scope.
- In the linked worktree, run Python through `D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe`.

---

### Task 1: Add Solver Models, Configuration, and Stable Serialization

**Files:**
- Modify: `src/papertrans/layout/models.py`
- Modify: `src/papertrans/layout/__init__.py`
- Create: `tests/test_layout_models.py`

**Interfaces:**
- Produces: `LayoutSolverConfig`, `LayoutSolverStatus`, `RegionAdjustment`, `LayoutCost`, `LayoutCandidate`, `CandidateGenerationStats`, `CandidateGenerationResult`, `PageLayoutProblem`, `LayoutSolverDiagnostics`, `LayoutSolverResult`, and `LayoutBuildResult`.
- Preserves: existing `LinePlacement`, `FlowLayout`, and `DocumentLayout` imports until Task 5 upgrades their serialized schema.

- [ ] **Step 1: Write failing configuration and serialization tests**

Create `tests/test_layout_models.py` with explicit defaults, validation cases, cost ordering, and secret-free candidate serialization:

```python
import math

import pytest

from papertrans.layout import (
    LayoutCandidate,
    LayoutCost,
    LayoutSolverConfig,
    LayoutSolverStatus,
    RegionAdjustment,
)


def test_solver_config_has_approved_defaults() -> None:
    config = LayoutSolverConfig()
    assert config.beam_width == 64
    assert config.font_step_pt == 0.5
    assert config.whitespace_step_pt == 2.0
    assert config.max_vertical_adjustment_pt == 12.0
    assert config.max_vertical_adjustment_ratio == 0.20
    assert config.preferred_font_scale == 0.90
    assert config.minimum_font_scale == 0.72
    assert config.minimum_font_size_pt == 6.0
    assert config.max_candidates_per_flow == 96


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("beam_width", 0),
        ("font_step_pt", math.nan),
        ("whitespace_step_pt", 0.0),
        ("max_vertical_adjustment_pt", -1.0),
        ("preferred_font_scale", 1.1),
        ("minimum_font_scale", 0.0),
        ("minimum_font_size_pt", math.inf),
        ("max_candidates_per_flow", 0),
    ],
)
def test_solver_config_rejects_invalid_values(field: str, value: object) -> None:
    values = LayoutSolverConfig().to_dict()
    values[field] = value
    with pytest.raises(ValueError, match="Invalid layout solver configuration"):
        LayoutSolverConfig(**values)


def test_layout_cost_uses_lexicographic_policy() -> None:
    normal_large = LayoutCost(0, 50, 0, 0, 0)
    compact_large = LayoutCost(1, 0, 1, 0, 0)
    normal_small = LayoutCost(2, 250, 0, 0, 0)
    compact_less_small = LayoutCost(2, 100, 1, 0, 0)
    assert normal_large < compact_large < compact_less_small < normal_small


def test_candidate_serialization_uses_fixed_status_and_no_text_identity() -> None:
    candidate = LayoutCandidate(
        candidate_id="lcand-0123456789abcdef",
        flow_id="flow-1",
        region_ids=("region-1",),
        variant="normal",
        original_font_size=10.0,
        font_size=9.0,
        adjustments=(RegionAdjustment("region-1", -2.0, 2.0),),
        placements=(),
        overflow_characters=0,
        blocked_line_slots=0,
        hard_violations=(),
        cost=LayoutCost(0, 100, 0, 4000, 0),
    )
    payload = candidate.to_dict()
    assert payload["candidate_id"] == "lcand-0123456789abcdef"
    assert payload["font_scale"] == 0.9
    assert "text" not in payload
    assert LayoutSolverStatus.SOLVED.value == "solved"
```

- [ ] **Step 2: Run Task 1 tests and verify RED**

Run:

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_models.py -v
```

Expected: collection fails because the new model names do not exist.

- [ ] **Step 3: Implement immutable models and fixed validation errors**

In `layout/models.py`:

- use `StrEnum` for `LayoutSolverStatus` with `SOLVED`, `REVIEW_INFEASIBLE`, and `REVIEW_SEARCH_LIMIT`;
- make configuration, adjustments, costs, and candidates frozen/slotted dataclasses;
- make `LayoutCost` ordered and expose `to_tuple()`/`to_dict()`;
- make `LayoutSolverConfig.__post_init__()` validate every finite/bound rule and raise exactly `ValueError("Invalid layout solver configuration")`;
- keep tuple fields immutable and emit lists from `to_dict()`;
- define `CandidateGenerationStats.candidate_cap_truncated_flow_ids` and fixed rejection counts;
- define `LayoutSolverResult` with status, ordered selected IDs, diagnostics, and no renderable layout;
- define `LayoutBuildResult.layout` as `DocumentLayout | None` and require it only for `SOLVED`;
- define `LayoutBuildResult.to_layout_dict()` and `to_solver_dict()` so review results serialize an
  empty `flows` list while solver diagnostics remain explicit;
- ensure candidate serialization contains placement text only inside the existing placement payload, never in identity or rejection diagnostics.

Export every public model from `layout/__init__.py`.

- [ ] **Step 4: Run model tests and the existing layout tests GREEN**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_models.py tests/test_cjk_layout.py -v
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check src/papertrans/layout tests/test_layout_models.py
```

Expected: all selected tests pass and Ruff exits zero.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/papertrans/layout/models.py src/papertrans/layout/__init__.py tests/test_layout_models.py
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "feat: define global layout solver models"
```

---

### Task 2: Extract Geometry Constraints and Independent Validation

**Files:**
- Create: `src/papertrans/layout/constraints.py`
- Create: `tests/test_layout_constraints.py`
- Modify: `src/papertrans/layout/cjk.py`

**Interfaces:**
- Consumes: `Document`, `Region`, `LinePlacement`, `LayoutCandidate`, `RegionAdjustment`, and `LayoutSolverConfig`.
- Produces: `Box`, `adjusted_region_box()`, `placement_box()`, `boxes_overlap()`, `protected_boxes_by_page()`, `candidate_conflicts()`, `candidate_hard_violations()`, and `validate_selection()`.
- Preserves: collision clearance `0.25`, line top factor `0.95`, and line bottom factor `0.15` from the current implementation.

- [ ] **Step 1: Write focused geometry and constraint failures**

Create synthetic regions/candidates in `tests/test_layout_constraints.py`. Cover exact boundary contact, clearance overlap, page/column escape, protected collision, translated collision, order inversion, font floors, and valid selection:

In that file, define `make_candidate()` to return one real `LayoutCandidate` containing one
`LinePlacement` at the supplied box, `make_region_map()` to return the two source `Region` objects,
and `validate_invalid_selection_fixture()` to build one page containing a fixed formula and return
the independent validator's reason codes. Use the literal flow IDs and geometry shown below.

```python
from papertrans.domain import BoundingBox, Document, Page, Region, RegionType, TextFlow
from papertrans.layout import LayoutCandidate, LayoutCost, LayoutSolverConfig, RegionAdjustment
from papertrans.layout.constraints import boxes_overlap, candidate_conflicts


def test_boxes_touching_at_edge_do_not_overlap_without_clearance() -> None:
    assert boxes_overlap((0, 0, 10, 10), (10, 0, 20, 10), clearance=0.0) is False
    assert boxes_overlap((0, 0, 10, 10), (10, 0, 20, 10), clearance=0.25) is True


def test_candidates_in_same_page_with_overlapping_lines_conflict() -> None:
    left = make_candidate("flow-a", x0=40, y0=100, x1=180, y1=110)
    right = make_candidate("flow-b", x0=40, y0=109.9, x1=180, y1=120)
    assert candidate_conflicts(left, right, make_region_map()) is True


def test_validator_reports_fixed_reason_codes_only() -> None:
    violations = validate_invalid_selection_fixture()
    assert set(violations) == {
        "font_floor",
        "page_bounds",
        "protected_overlap",
        "reading_order",
    }
    assert all("fixture translation" not in item for item in violations)
```

The helper functions in this test file must construct real dataclasses; do not mock constraint
functions.

- [ ] **Step 2: Run constraints tests and verify RED**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_constraints.py -v
```

Expected: import fails because `layout.constraints` does not exist.

- [ ] **Step 3: Implement pure constraint functions**

Move the box constants and overlap helpers out of `cjk.py`. Define `Box` as
`tuple[float, float, float, float]`. Implement the exact public signatures
`adjusted_region_box(region: Region, adjustment: RegionAdjustment) -> Box`,
`candidate_hard_violations(candidate: LayoutCandidate, document: Document, config:
LayoutSolverConfig) -> Sequence[str]`, and `validate_selection(selected:
Sequence[LayoutCandidate], document: Document, config: LayoutSolverConfig) -> Sequence[str]`.

Use fixed lowercase reason codes. Validate the final selection from original domain geometry, not
from beam-state acceptance flags. Respect `region.metadata["column_index"]`; horizontal coordinates
must remain equal to the source region in M5.1. Validate cross-page candidates only against their
existing `TextFlow.page_numbers` and `region_ids`.

Update `cjk.py` to import the extracted overlap and placement helpers without changing current
runtime output.

- [ ] **Step 4: Run constraint, existing layout, and render tests GREEN**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_constraints.py tests/test_cjk_layout.py tests/test_translated_render.py -v
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check src/papertrans/layout tests/test_layout_constraints.py
```

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/papertrans/layout/constraints.py src/papertrans/layout/cjk.py tests/test_layout_constraints.py
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "refactor: isolate layout constraints"
```

---

### Task 3: Generate Deterministic Translation and Whitespace Candidates

**Files:**
- Create: `src/papertrans/layout/candidates.py`
- Create: `tests/test_layout_candidates.py`
- Modify: `src/papertrans/layout/cjk.py`
- Modify: `src/papertrans/layout/models.py`

**Interfaces:**
- Consumes: `Document`, `TranslationResult`, `CJKFontResolver`, `LayoutSolverConfig`, and constraint helpers.
- Produces: `generate_layout_candidates(document, translations, config, font_resolver=None) -> CandidateGenerationResult`.
- Produces: canonical `candidate_id` values and per-flow truncation/rejection diagnostics without full rejected text.

- [ ] **Step 1: Write candidate generation tests**

Create `tests/test_layout_candidates.py` with real synthetic `Document` objects. Required cases:

Define the test helpers in the same file. `document_with_one_flow()` creates one 220x120 paragraph
region at `(50, 100)` with `column_index=1`; `document_with_region_height()` changes only that
height; `translations()` returns normal and compact `TranslationResult` values for `flow-1`;
`generate_fixture_candidates()` builds the same two-flow document with normal or reversed mapping
insertion order; `candidate_ids()` returns IDs sorted by flow; and `generate_many_candidates()`
uses a 100pt-high region with both variants so the configured cap is exercised.

```python
def test_font_sizes_include_original_preferred_and_exact_floor() -> None:
    result = generate_layout_candidates(document_with_one_flow(font_size=10.0), translations(), LayoutSolverConfig())
    sizes = {candidate.font_size for candidate in result.candidates_by_flow["flow-1"]}
    assert 10.0 in sizes
    assert 9.0 in sizes
    assert 7.2 in sizes
    assert all(size >= 7.2 for size in sizes)


def test_vertical_adjustments_are_discrete_and_capped() -> None:
    result = generate_layout_candidates(document_with_region_height(40.0), translations(), LayoutSolverConfig())
    adjustments = {
        (item.top_delta, item.bottom_delta)
        for candidate in result.candidates_by_flow["flow-1"]
        for item in candidate.adjustments
    }
    assert all(abs(value) <= 8.0 for pair in adjustments for value in pair)
    assert (-2.0, 0.0) in adjustments
    assert (0.0, 2.0) in adjustments


def test_candidate_ids_and_order_ignore_input_mapping_order() -> None:
    first = generate_fixture_candidates(reverse=False)
    second = generate_fixture_candidates(reverse=True)
    assert candidate_ids(first) == candidate_ids(second)


def test_candidate_cap_is_deterministic_and_marks_search_truncation() -> None:
    config = LayoutSolverConfig(max_candidates_per_flow=3)
    result = generate_many_candidates(config)
    assert len(result.candidates_by_flow["flow-1"]) == 3
    assert result.stats.candidate_cap_truncated_flow_ids == ("flow-1",)
```

Also assert protected obstacles reject affected line slots, no adjustment changes x coordinates or
column membership, normal/compact variants are both present, dominance pruning is stable, and
serialized rejected diagnostics exclude a translation sentinel.

- [ ] **Step 2: Run candidate tests and verify RED**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_candidates.py -v
```

- [ ] **Step 3: Refactor line layout into a pure candidate generator**

Move `_take_line`, `_flow_font_size`, `_flow_bold`, and the single-flow layout attempt from `cjk.py`
into `candidates.py`. Keep CJK punctuation rules unchanged. Implement the exact public signature
`generate_layout_candidates(document: Document, translations: dict[str, TranslationResult],
config: LayoutSolverConfig, font_resolver: CJKFontResolver | None = None) ->
CandidateGenerationResult`.

Generation rules must exactly follow the specification:

- original, exact 90%, 0.5pt steps, and exact `max(6pt, original * 0.72)`;
- vertical shapes `none`, `expand_up`, `expand_down`, `expand_symmetric`, `shift_up`, and
  `shift_down` in 2pt steps plus the exact cap;
- fixed protected boxes are occupancy; translated candidates are not shared occupancy;
- use canonical rounded JSON and SHA-256 for IDs;
- compute local cost components in integers;
- remove dominated candidates, stable-sort, cap at 96, and mark truncation.

Do not store rejected full translation strings in `CandidateGenerationResult.to_dict()`.

- [ ] **Step 4: Run candidates, constraints, and legacy layout tests GREEN**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_candidates.py tests/test_layout_constraints.py tests/test_cjk_layout.py -v
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check src/papertrans/layout tests/test_layout_candidates.py
```

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/papertrans/layout/candidates.py src/papertrans/layout/cjk.py src/papertrans/layout/models.py tests/test_layout_candidates.py
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "feat: generate deterministic layout candidates"
```

---

### Task 4: Implement Deterministic Page-Component Beam Search

**Files:**
- Create: `src/papertrans/layout/solver.py`
- Create: `tests/test_layout_solver.py`
- Modify: `src/papertrans/layout/models.py`

**Interfaces:**
- Consumes: `CandidateGenerationResult`, `Document`, `LayoutSolverConfig`, and constraint helpers.
- Produces: `build_page_problems()` and `solve_layout(document, generation, config) -> LayoutSolverResult`.
- Guarantees: stable variable/candidate order, explicit truncation classification, bound cross-page candidate selection, and independent final validation.

- [ ] **Step 1: Write the greedy-trap and determinism tests**

Create manual candidates with fixed placements so solver behavior does not depend on fonts:

Define every named fixture helper in `tests/test_layout_solver.py`. `greedy_trap_generation()` uses
two flows: flow A has a lower-cost wide box `(40, 100, 180, 120)` and a narrow box
`(40, 100, 100, 120)`; flow B has only `(100, 100, 180, 120)`. The only complete solution is A's
narrow candidate plus B. The permutation helper reverses page, flow, candidate-map, and candidate
tuple insertion order without changing IDs. The infeasible helper gives both flows one overlapping
candidate. The search-limit helper provides two states at the first variable and makes only the
state pruned by beam width one lead to a complete solution. The cross-page helper gives one flow
placements in `p1-body` and `p2-body`, with no alternate region IDs.

```python
def test_beam_search_finds_combination_that_first_fit_greedy_misses() -> None:
    generation = greedy_trap_generation()
    result = solve_layout(greedy_trap_document(), generation, LayoutSolverConfig(beam_width=8))
    assert result.status is LayoutSolverStatus.SOLVED
    assert result.selected_candidate_ids == (
        "lcand-flow-a-narrow",
        "lcand-flow-b-only-fit",
    )
    assert result.diagnostics.final_validation_passed is True


def test_permuting_flows_candidates_and_pages_is_byte_stable() -> None:
    first = solve_permutation(reverse=False).to_dict()
    second = solve_permutation(reverse=True).to_dict()
    assert first == second


def test_exhaustive_failure_is_infeasible() -> None:
    result = solve_layout(infeasible_document(), infeasible_generation(), LayoutSolverConfig(beam_width=64))
    assert result.status is LayoutSolverStatus.REVIEW_INFEASIBLE
    assert result.selected_candidate_ids == ()


def test_truncated_failure_is_search_limit() -> None:
    result = solve_layout(search_limit_document(), search_limit_generation(), LayoutSolverConfig(beam_width=1))
    assert result.status is LayoutSolverStatus.REVIEW_SEARCH_LIMIT
    assert result.diagnostics.beam_truncated is True


def test_cross_page_flow_uses_one_bound_candidate() -> None:
    result = solve_cross_page_binding()
    selected = selected_candidates(result)
    assert selected["flow-cross-page"].region_ids == ("p1-body", "p2-body")
    assert {line.page_number for line in selected["flow-cross-page"].placements} == {1, 2}
```

Add tests for candidate-cap truncation classification, fewest-candidates/highest-degree/ID variable
ordering, cost policy, style variance tie-breaking, movement tie-breaking, collision rejection, and a
corrupted selected set rejected by independent validation.

- [ ] **Step 2: Run solver tests and verify RED**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_solver.py -v
```

- [ ] **Step 3: Implement page problems, components, and beam states**

Implement internal immutable `_BeamState` and the exact public signatures
`build_page_problems(document: Document, generation: CandidateGenerationResult) ->
Sequence[PageLayoutProblem]` and `solve_layout(document: Document, generation:
CandidateGenerationResult, config: LayoutSolverConfig) -> LayoutSolverResult`.

Solve independent pages separately. When a `TextFlow` touches more than one page, join only those
page problems into a connected component and select that flow once; do not move text across pages.
Merge solved component selections in stable page/flow order.

At every beam level:

- order variables by viable candidate count, descending conflict degree, then flow ID;
- order candidates by numeric cost tuple and candidate ID;
- reject hard conflicts immediately;
- sort states by accumulated page cost then selected candidate-ID tuple;
- record whether more than `beam_width` states existed before truncation.

After a complete selection, call `validate_selection()` again. A contradiction raises a new fixed
`LayoutInvariantError("Selected layout failed independent validation")` without including text.

- [ ] **Step 4: Run solver and upstream unit tests GREEN**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_solver.py tests/test_layout_candidates.py tests/test_layout_constraints.py tests/test_layout_models.py -v
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check src/papertrans/layout tests/test_layout_solver.py
```

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/papertrans/layout/solver.py src/papertrans/layout/models.py tests/test_layout_solver.py
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "feat: solve page layouts with deterministic beam search"
```

---

### Task 5: Make the Global Solver the CJK Facade and Add QA Metrics

**Files:**
- Modify: `src/papertrans/layout/cjk.py`
- Modify: `src/papertrans/layout/models.py`
- Modify: `src/papertrans/layout/__init__.py`
- Create: `src/papertrans/qa/layout.py`
- Modify: `src/papertrans/qa/__init__.py`
- Modify: `tests/test_cjk_layout.py`
- Create: `tests/test_global_layout.py`

**Interfaces:**
- Changes: `build_cjk_layout(document, translations, config=None, font_resolver=None) -> LayoutBuildResult`.
- Produces: schema `0.2` `DocumentLayout`, selected `FlowLayout.candidate_id` and adjustments, and `build_layout_stats()`.
- Removes: runtime use of translated-flow shared occupancy and automatic greedy fallback.

- [ ] **Step 1: Write facade, policy, and order-invariance tests**

Update existing tests to unwrap `result.layout` only when status is solved. Add:

Define `policy_document()` as one paragraph at 10pt with enough height for normal text at 9pt,
`policy_translations()` with a longer normal and shorter compact result, `build_order_fixture()` as
the two-flow page from the solver permutation test passed through the facade, and
`impossible_document()` as a 20x8pt region whose normal and compact translations exceed every
allowed candidate. `impossible_translations()` returns those two oversized variants for the
fixture's single flow.

```python
def test_global_facade_selects_balanced_translation_policy() -> None:
    result = build_cjk_layout(policy_document(), policy_translations(), LayoutSolverConfig(beam_width=64))
    assert result.status is LayoutSolverStatus.SOLVED
    assert result.layout is not None
    selected = result.layout.flows[0]
    assert selected.variant == "normal"
    assert selected.font_size / selected.original_font_size >= 0.90


def test_global_facade_is_independent_of_text_flow_order() -> None:
    first = build_order_fixture(reverse=False)
    second = build_order_fixture(reverse=True)
    assert first.to_dict() == second.to_dict()


def test_review_result_has_no_renderer_consumable_layout() -> None:
    result = build_cjk_layout(impossible_document(), impossible_translations())
    assert result.status is LayoutSolverStatus.REVIEW_INFEASIBLE
    assert result.layout is None
    assert result.to_layout_dict()["flows"] == []
```

Assert schema `0.2`, all legacy quality metrics, new solver/search/adjustment/style metrics, and no
full rejected text in solver diagnostics.

- [ ] **Step 2: Run facade tests and verify RED**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_cjk_layout.py tests/test_global_layout.py -v
```

- [ ] **Step 3: Replace facade orchestration and implement layout QA**

`build_cjk_layout()` must:

1. create/validate `LayoutSolverConfig`;
2. call `generate_layout_candidates()`;
3. call `solve_layout()`;
4. return review immediately without constructing renderable flows;
5. convert selected candidates to stable `FlowLayout` values;
6. call independent constraint validation once more;
7. calculate stats through `qa.layout.build_layout_stats()`;
8. return `LayoutBuildResult` with fonts and schema `0.2` layout.

Delete translated-flow shared occupancy from the runtime path. If old helpers remain for temporary
tests, prefix them `_legacy_` and ensure no production call site references them; remove them before
Task 7 completion.

`build_layout_stats()` must return current metrics plus solver status, candidate/viable counts,
expanded/rejected/pruned state counts, truncation flags, tier counts, total/max adjustment,
same-type scale variance, selected cost fields, and final-validation status.

- [ ] **Step 4: Run all layout and renderer tests GREEN**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_layout_models.py tests/test_layout_constraints.py tests/test_layout_candidates.py tests/test_layout_solver.py tests/test_cjk_layout.py tests/test_global_layout.py tests/test_translated_render.py -v
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check src/papertrans/layout src/papertrans/qa tests/test_global_layout.py tests/test_cjk_layout.py
```

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/papertrans/layout src/papertrans/qa tests/test_cjk_layout.py tests/test_global_layout.py
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "refactor: make global solving the cjk layout path"
```

---

### Task 6: Integrate Review-Safe Job Artifacts and CLI Beam Control

**Files:**
- Modify: `src/papertrans/translation_job.py`
- Modify: `src/papertrans/mock_translation.py`
- Modify: `src/papertrans/cli.py`
- Modify: `tests/test_translation_job.py`
- Modify: `tests/test_mock_translation_pipeline.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Adds keyword-only `layout_beam_width: int = 64` to `run_translation_job()` and the matching mock wrapper.
- Adds: `TranslationJobResult.layout_solver_json: Path`, `status: str`, and `output_pdf: Path | None`.
- Adds CLI: `--layout-beam-width`, positive integer, default `64`.
- Preserves: provider construction, provider close semantics, cache identity, translation replay, and protected-token failure behavior.

- [ ] **Step 1: Write review artifact and stale-output safety tests**

Add job tests using a deliberately impossible tiny PDF and cached deterministic provider:

Define `create_impossible_pdf()` in `tests/test_translation_job.py` as a 200x200 page with one
20x8pt text box containing a translatable sentence. Define `prepare_review_rerun()` to populate a
shared cache by running the same deterministic provider once, then return a second output directory,
the cache directory, and a provider whose `calls` list must remain empty on replay.

```python
def test_infeasible_layout_writes_review_artifacts_without_pdf(tmp_path: Path) -> None:
    result = run_translation_job(
        create_impossible_pdf(tmp_path / "source.pdf"),
        tmp_path / "review",
        DeterministicProvider(),
    )
    assert result.status == "REVIEW"
    assert result.output_pdf is None
    assert result.layout_json.is_file()
    assert result.layout_solver_json.is_file()
    assert result.report["output_pdf_written"] is False
    assert result.report["layout"]["solver_status"] == "review_infeasible"
    assert not (tmp_path / "review" / "output.pdf").exists()


def test_review_run_preserves_existing_valid_output_and_cache(tmp_path: Path) -> None:
    output_dir, cache_dir, provider = prepare_review_rerun(tmp_path)
    prior = output_dir / "output.pdf"
    prior.write_bytes(b"previous-valid-output")
    result = run_translation_job(create_impossible_pdf(tmp_path / "source.pdf"), output_dir, provider, cache_dir=cache_dir)
    assert prior.read_bytes() == b"previous-valid-output"
    assert result.report["output_pdf_written"] is False
    assert provider.calls == []
    assert result.report["provider_execution"]["usage"]["input_tokens"] == 0
```

Add CLI tests that default to 64, reject `0`, negative values, and an integer overflow-like string,
pass the selected width to the job, print `Output PDF: not written` for review, and never print a
stale path as a new output.

- [ ] **Step 2: Run job and CLI tests and verify RED**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_translation_job.py tests/test_mock_translation_pipeline.py tests/test_cli.py -v
```

- [ ] **Step 3: Implement atomic solved/review branches**

In `run_translation_job()`:

- write `translations.json` before layout;
- call the global facade with `LayoutSolverConfig(beam_width=layout_beam_width)`;
- atomically write schema `0.2` `layout.json` and `layout-solver.json` for every result;
- on review, write schema `0.2` `translation-report.json`, set `status="REVIEW"`, set
  `output_pdf_written=False`, return `output_pdf=None`, and do not call renderer or roundtrip QA;
- on solved, render to the existing UUID temporary path and replace `output.pdf` only after render
  succeeds;
- never delete or replace a prior output on review;
- preserve cache/provider/protection artifacts and statistics.

In CLI validation, require `--layout-beam-width > 0`. Pass it through without adding it to provider
configuration or cache identity. Keep cleanup error precedence from the M4.3 implementation.

- [ ] **Step 4: Run job, CLI, provider, and render tests GREEN**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_translation_job.py tests/test_mock_translation_pipeline.py tests/test_cli.py tests/test_provider_translation_pipeline.py tests/test_translated_render.py -v
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check src/papertrans/translation_job.py src/papertrans/mock_translation.py src/papertrans/cli.py tests/test_translation_job.py tests/test_cli.py
```

- [ ] **Step 5: Commit Task 6**

```powershell
git add src/papertrans/translation_job.py src/papertrans/mock_translation.py src/papertrans/cli.py tests/test_translation_job.py tests/test_mock_translation_pipeline.py tests/test_cli.py
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "feat: stop rendering review-only layouts"
```

---

### Task 7: Add Full-PDF Regression Gates and Complete M5.1 Documentation

**Files:**
- Create: `tests/test_global_layout_pipeline.py`
- Modify: `tests/test_provider_translation_pipeline.py`
- Modify: `README.md`
- Modify: `docs/BUILD_FLOW.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: deterministic full-PDF evidence for solved, greedy-trap, review, cache replay, and permutation invariance.
- Changes milestone only after all unit, provider, PDF, manual-paper, full-suite, and Ruff gates pass.

- [ ] **Step 1: Create deterministic PDF and permutation acceptance tests**

Create a two-column PyMuPDF fixture whose overlapping source regions give two flows multiple valid
choices, where the first local choice blocks the second but beam search selects a page-wide valid
combination. The test must assert:

Define `run_global_fixture()` in the new test file to create the fixture and execute a mock
translation job with a shared cache. Define `selected_ids()` to read and return the ordered
`selected_candidate_ids` from `layout-solver.json`. Define `quality_without_runtime()` to copy only
deterministic layout, page, link, protection, and gate metrics while excluding wall-clock duration
and output paths. Flow-order permutation remains a direct facade test in Task 5; the full-PDF test
does not add a production extraction injection seam.

```python
def test_global_solver_renders_greedy_trap_without_overlap(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    first = run_global_fixture(tmp_path / "first", cache_dir)
    second = run_global_fixture(tmp_path / "second", cache_dir)
    assert first.status == second.status == "PASS"
    assert first.report["layout"]["solver_status"] == "solved"
    assert first.report["layout"]["translated_line_overlap_count"] == 0
    assert first.report["layout"]["protected_region_overlap_count"] == 0
    assert first.report["layout"]["overflow_flow_count"] == 0
    assert selected_ids(first.layout_solver_json) == selected_ids(second.layout_solver_json)
    assert quality_without_runtime(first.report) == quality_without_runtime(second.report)
```

Add a separate impossible fixture that asserts review diagnostics and absence of a newly written
PDF. Extend the named-provider test to assert solver artifacts, unchanged secret scans, exact
protected-value multiplicity, cache replay, and zero replay billing.

- [ ] **Step 2: Run deterministic PDF tests**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest tests/test_global_layout_pipeline.py tests/test_provider_translation_pipeline.py -v
```

Expected: all new PDF tests pass without a live provider or network.

- [ ] **Step 3: Run the entire deterministic suite and Ruff**

```powershell
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check .
```

Fix production defects through `superpowers:systematic-debugging`; do not weaken gates or increase
beam width only to hide an invalid constraint implementation.

- [ ] **Step 4: Run the user-paper M5.1 quality gates**

Use the ignored PDFs under `D:\project_for_codex\clean_translate_for_pdf\test_pdf`. Run all four
normal-length papers with `--provider mock --layout-beam-width 64` into fresh ignored output
directories. Run Fast R-CNN again with `--length-factor 1.3`. For each run verify:

- CLI reports `Quality gate: PASS` and solver status `solved`;
- all eight artifacts exist, including `layout-solver.json`;
- page count/dimensions and links are unchanged;
- overflow, translated overlap, protected overlap, and new sub-6pt counts are zero;
- minimum scale is at least `0.72`;
- selected IDs and non-runtime metrics repeat exactly on a cached second run;
- second-run provider calls and fresh usage are zero.

Record paper names and metrics in the Task 7 implementation report; do not commit the PDFs or
generated artifacts.

- [ ] **Step 5: Update milestone documentation only after gates pass**

Update all three documents consistently:

- `README.md`: explain page-level global solving, fixed page count, controlled whitespace borrowing,
  `--layout-beam-width`, solved/review artifacts, and no-render review behavior;
- `docs/BUILD_FLOW.md`: mark M5.1 complete, record deterministic/global/PDF gates, and identify M5.2
  as document-level consistency and solver-scaling evaluation;
- `AGENTS.md`: mark M5.1 complete, preserve every M4.3 rule, and state M5.2 is next.

Keep M5-C context enhancement deferred. Keep OCR, models, GUI, Google Translate, and a specialized
optimizer outside the completed milestone.

- [ ] **Step 6: Re-run final verification after documentation changes**

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider
& 'D:\project_for_codex\clean_translate_for_pdf\.venv\Scripts\python.exe' -m ruff check .
git diff --check
git status --short
```

Expected: all tests pass, Ruff/diff checks exit zero, and only the five Task 7 files are intentional
changes.

- [ ] **Step 7: Commit Task 7**

```powershell
git add tests/test_global_layout_pipeline.py tests/test_provider_translation_pipeline.py README.md docs/BUILD_FLOW.md AGENTS.md
git -c user.name="Codex" -c user.email="codex@openai.com" commit -m "docs: complete the m5.1 global layout milestone"
```

---

## Final Review Checklist

- [ ] One deterministic candidate is selected per translatable flow.
- [ ] Normal/compact/font policy matches the approved 90%/72%/6pt hierarchy.
- [ ] Whitespace borrowing is vertical, discrete, capped, page-local, and column-local.
- [ ] Flow/candidate/page input permutations produce identical selected candidate IDs and metrics.
- [ ] Cross-page flows use one bound candidate and no new regions.
- [ ] No overflow, translated overlap, protected overlap, page change, or silent content loss occurs
  in a solved result.
- [ ] Review-infeasible and review-search-limit states are distinguished.
- [ ] Candidate-cap or beam truncation can never claim proven infeasibility.
- [ ] Review results preserve cache and prior valid output while writing no new PDF.
- [ ] Increasing beam width causes no external provider call when translations are cached.
- [ ] Solver diagnostics contain no rejected full text, API key, or provider secret.
- [ ] Existing M4.3 provider, protection, retry, cache, usage, cost, CLI, and cleanup tests pass.
- [ ] Four normal papers and Fast R-CNN 1.3x pass the M5.1 PDF gates.
- [ ] No greedy runtime fallback, optimizer dependency, OCR, model download, GUI, Google adapter, or
  context/terminology work was added.
- [ ] README, BUILD_FLOW, and AGENTS milestone state agree after final verification.

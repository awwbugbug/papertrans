# M5.1 Deterministic Global Layout Solver Design

**Status:** Approved design for implementation

**Milestone:** M5.1, page-level global layout solving

**Date:** 2026-07-31

## 1. Goal

Replace the current flow-order-dependent CJK layout selection with a deterministic page-level
global solver. The solver must choose one complete layout candidate for every translatable
`TextFlow`, minimize layout distortion across the page, and preserve every M4.3 protection,
provider, cache, privacy, and reliability gate.

M5.1 keeps the original page count. If no valid combination fits inside the permitted geometry,
the job enters `REVIEW`; it must not clip text, silently omit content, add a page, or produce a new
incomplete `output.pdf`.

## 2. Approved Product Decisions

- The page count is immutable.
- Solving is page-level. Content may not be moved to another page or a newly created region.
- A cross-page `TextFlow` selects one bound candidate across its existing regions and pages. This
  binding guarantees consistency but does not enable multi-page reflow.
- Translation/layout quality uses a balanced priority:
  1. normal translation at 90%-100% of the original font size;
  2. compact translation at 90%-100%;
  3. candidates below 90%, where the larger readable font wins;
  4. normal translation wins over compact translation at an equal font size.
- Font size may never fall below both the existing 72% scale floor and the absolute 6pt floor.
- Text may borrow whitespace only through controlled vertical adjustment inside the same page and
  column. Horizontal column boundaries remain fixed in M5.1.
- The first solver is a deterministic beam search. M5.1 does not add OR-Tools or another optimizer.

## 3. Non-Goals

M5.1 does not add or change:

- OCR, OCR model weights, model downloads, or scanned-document handling;
- GUI or interactive editing;
- Google Translate support;
- chapter-level context, terminology tables, adjacent-segment context, or cross-segment batching;
- automatic provider failover;
- free page reflow, new pages, new columns, or cross-column movement;
- a general nonlinear or mixed-integer optimization dependency.

## 4. Existing Limitation

`build_cjk_layout()` currently visits `Document.text_flows` in sequence. As soon as it selects a
candidate for one flow, that flow's placements are added to shared page occupancy. A candidate for
a later flow therefore depends on input order. The implementation can produce a locally valid
choice that prevents a better page-wide combination, and permuting otherwise identical flows can
change the result.

M5.1 separates candidate generation from page-wide selection. Candidate generation sees fixed
page geometry and protected objects, but it does not reserve space on behalf of other translated
flows. The solver evaluates translated-flow collisions only after all candidates exist.

## 5. Architecture

```text
Document + TranslationResult map + LayoutSolverConfig
                    |
                    v
          deterministic candidate generation
                    |
                    v
     PageLayoutProblem objects + cross-page bindings
                    |
                    v
          deterministic beam-search solver
                    |
                    v
       independent final constraint validation
                    |
          +---------+---------+
          |                   |
        SOLVED              REVIEW
          |                   |
          v                   v
   DocumentLayout       diagnostics only;
   and PDF render       no new PDF render
```

The modules have the following responsibilities:

- `layout/candidates.py`: enumerate and dominance-prune candidates for each flow.
- `layout/constraints.py`: build collision geometry and validate hard constraints.
- `layout/solver.py`: order variables, expand beam states, score them, and classify the result.
- `layout/models.py`: define JSON-serializable candidate, problem, cost, adjustment, and result
  models.
- `layout/cjk.py`: remain the public layout facade and orchestrate the new components.
- `translation_job.py`: persist solver artifacts and stop before rendering when the result requires
  review.
- `qa/`: own solver-related regression metrics and quality-gate assertions.

The translation provider remains unaware of layout and rendering. The renderer receives only a
validated `DocumentLayout` and never calls the solver or a provider.

## 6. Data Model

### 6.1 LayoutSolverConfig

`LayoutSolverConfig` is immutable and JSON-serializable:

```python
@dataclass(frozen=True, slots=True)
class LayoutSolverConfig:
    beam_width: int = 64
    font_step_pt: float = 0.5
    whitespace_step_pt: float = 2.0
    max_vertical_adjustment_pt: float = 12.0
    max_vertical_adjustment_ratio: float = 0.20
    preferred_font_scale: float = 0.90
    minimum_font_scale: float = 0.72
    minimum_font_size_pt: float = 6.0
    max_candidates_per_flow: int = 96
```

Validation requires finite values, `beam_width > 0`, positive step sizes, nonnegative adjustment
limits, `0 < minimum_font_scale <= preferred_font_scale <= 1`, positive minimum font size, and a
positive candidate cap. Invalid configuration fails before candidate generation with fixed errors
that contain no paper text.

### 6.2 RegionAdjustment

`RegionAdjustment` records the geometry difference from one original region:

```python
@dataclass(frozen=True, slots=True)
class RegionAdjustment:
    region_id: str
    top_delta: float
    bottom_delta: float
```

M5.1 keeps `x0` and `x1` unchanged. Negative `top_delta` borrows whitespace above the region;
positive `bottom_delta` borrows whitespace below it. A pure vertical shift is represented by equal
signed changes to both boundaries. All values are rounded to three decimal places for identity and
serialization.

### 6.3 LayoutCandidate

Each `LayoutCandidate` contains:

- stable `candidate_id`;
- `flow_id` and the original ordered `region_ids`;
- `variant`: `normal` or `compact`;
- `font_size` and `font_scale`;
- region adjustments;
- final `LinePlacement` values across existing regions;
- overflow character count;
- blocked fixed-object slot count;
- hard-violation codes;
- a structured cost vector;
- diagnostic markers explaining generation, pruning, or rejection.

Candidate IDs use a canonical JSON representation of schema version, flow ID, variant, rounded
font size, and ordered region adjustments. The ID is `lcand-` plus the first 16 hexadecimal
characters of SHA-256. It never contains translation text, API configuration, or a secret.

Rejected candidate diagnostics store counts, geometry, IDs, and fixed reason codes. They do not
store rejected full translation text. Selected placements retain the text required by the renderer
in `layout.json`, consistent with the existing artifact contract.

### 6.4 PageLayoutProblem

`PageLayoutProblem` contains:

- page number and immutable page bounds;
- deterministic column bounds derived from existing page regions;
- fixed protected boxes for formulas, figures, tables, and other non-translatable content;
- ordered flow IDs that touch the page;
- candidate IDs available to each flow;
- cross-page binding IDs;
- a conservative conflict graph indicating which candidate pairs may collide.

The problem never contains raw PyMuPDF objects.

### 6.5 LayoutCost

The cost is a lexicographically compared tuple, not one opaque floating-point sum:

```text
quality_tier
font_loss_milli
compact_penalty
vertical_adjustment_milli
style_scale_variance_milli
stable_candidate_tiebreak
```

`quality_tier` is:

- `0`: normal and font scale >= 0.90;
- `1`: compact and font scale >= 0.90;
- `2`: either variant below 0.90.

Within tier 2, font loss is compared before compact penalty, so a substantially larger compact
candidate can beat an unreadably small normal candidate. Within equal font size and geometry,
normal translation wins. Style variance is a soft page-level penalty among flows of the same
`RegionType`; it does not force all paragraphs to use one font size.

### 6.6 LayoutSolverResult

The result status is one of:

- `SOLVED`: a complete combination passed independent validation;
- `REVIEW_INFEASIBLE`: no complete state exists and neither beam truncation nor candidate-cap
  truncation occurred, so the fully enumerated candidate problem is proven infeasible;
- `REVIEW_SEARCH_LIMIT`: no complete state was found after at least one beam truncation, so the
  solver has not proven infeasibility.

The result records selected candidate IDs, aggregate cost, beam width, expanded/pruned state
counts, truncation markers, rejection counts by reason, involved flow IDs, and the smallest observed
conflict set. It must not label the observed set as a mathematically minimal unsatisfiable core.

## 7. Candidate Generation

### 7.1 Font Sizes and Translation Variants

For each translatable flow, generate both available translation variants over a deterministic size
sequence:

- original font size;
- the exact 90% preferred breakpoint when it is not already present;
- 0.5pt decrements;
- the exact lower bound `max(6pt, original_size * 0.72)`.

Duplicate rounded sizes are removed. Normal candidates precede compact candidates only for stable
enumeration; solver cost, not enumeration order, determines selection.

### 7.2 Controlled Whitespace Borrowing

The vertical cap for one original region boundary is:

```text
min(12pt, original_region_height * 0.20)
```

Adjustment values are enumerated in deterministic 2pt steps plus the exact cap. Candidate shapes
include:

- no adjustment;
- expand upward;
- expand downward;
- symmetric expansion;
- shift upward;
- shift downward.

Every adjustment must remain within the same page and derived column. It may not cross a fixed
protected box. Collisions with other translated flows are not rejected at generation time; they are
solver constraints.

The generator keeps reading-order anchors. A candidate may enlarge or move its allocated vertical
box, but it may not invert the original order of flow anchors within a column.

### 7.3 Dominance Pruning and Candidate Cap

Candidate A dominates candidate B for the same flow when A has:

- the same variant and font size;
- no more overflow or hard violations;
- no greater adjustment magnitude;
- placements occupying a subset of B's geometry.

Dominated candidates are removed using stable sorting. If more than 96 nondominated candidates
remain, keep the best 96 by the candidate-local portion of the cost vector and record
`candidate_cap_truncated = true`. Candidate-cap truncation is treated like search truncation when
classifying an unsuccessful solve; it cannot produce `REVIEW_INFEASIBLE`.

## 8. Constraint System

Hard constraints require:

- exactly one selected candidate per translatable flow;
- zero overflow characters;
- zero hard-violation codes;
- font size and scale at or above configured floors;
- every placement inside its adjusted region, column, and original page;
- no placement overlap with protected content;
- no overlap between selected candidates, using the existing collision clearance;
- unchanged page numbers and original region membership;
- preserved flow anchor order inside each column;
- one consistent candidate selection for a cross-page flow.

The final selected combination is rechecked by an independent validator that does not reuse beam
state acceptance flags. A validation failure is an invariant error, not a `SOLVED` result.

## 9. Deterministic Beam Search

Variables are ordered by:

1. fewest viable candidates;
2. highest conflict-graph degree;
3. stable flow ID.

Candidates for one variable are ordered by cost vector and candidate ID. A beam state contains
selected IDs, per-page occupancy, accumulated structured cost, and diagnostic counts. Expansion
rejects a state immediately when a new candidate violates a hard constraint with any previously
selected candidate.

After each variable, states are sorted by accumulated lexicographic cost followed by the ordered
candidate-ID tuple. Only the first `beam_width` states survive. The solver records whether states
were truncated at every level.

Cross-page flows are selected once and their placements are injected into every touched page
problem. This is a binding coordinator over page problems, not permission to move content between
pages. All geometry budgets remain page-local.

Changing the input order of pages, flows, translation mappings, or candidate mappings must not
change selected candidate IDs or serialized layout output.

## 10. Pipeline and Artifact Behavior

`build_cjk_layout()` remains the public facade but returns solver status and diagnostics alongside
the selected `DocumentLayout` when solved.

`layout.json` advances to schema version `0.2` and always records `solver_status`. For `SOLVED`, it
contains the validated selected layout. For a review status, it contains no renderer-consumable
placements and points to `layout-solver.json`; this prevents a partial layout from being mistaken
for a complete result. `layout-solver.json` contains configuration, status, cost, candidate counts,
selected candidate IDs, rejection reason counts, adjustment summaries, and conflict diagnostics.

On `SOLVED`:

1. write both layout artifacts atomically;
2. render to a temporary PDF;
3. run all existing layout, protection, page, link, and visual QA gates;
4. atomically replace `output.pdf` only after render succeeds.

On a review status:

1. persist translations, protection state, provider run state, `layout.json` diagnostic content,
   `layout-solver.json`, and `translation-report.json`;
2. set the job/report status to `REVIEW` and identify infeasible versus search-limit status;
3. do not create or replace `output.pdf`;
4. preserve any prior valid `output.pdf` unchanged and explicitly record
   `output_pdf_written = false`, preventing it from being mistaken for this run's output;
5. preserve all successful provider cache entries.

Changing `--layout-beam-width` reruns only local candidate generation and solving. It does not alter
provider cache identity and does not call a translation provider again when translations are
cached.

The CLI adds `--layout-beam-width`, a finite positive integer with default 64. It does not expose
arbitrary objective weights in M5.1.

## 11. Error Handling

- Invalid solver configuration fails before layout with a fixed `ValueError` message.
- `REVIEW_INFEASIBLE` and `REVIEW_SEARCH_LIMIT` are expected job outcomes, not exceptions.
- Internal candidate or validator contradictions raise a sanitized `LayoutInvariantError` and mark
  the job failed; exception messages do not contain full paper text.
- Rendering is never attempted for a review or invariant-failure result.
- Provider failures, protected-token failures, and cache behavior retain their M4.3 semantics.
- No automatic fallback to the legacy greedy algorithm occurs.

The legacy implementation may remain temporarily as a test oracle during M5.1 development, but it
is not a runtime fallback and is removed or made test-private before the milestone is marked
complete.

## 12. Quality Metrics

Existing metrics remain mandatory:

- overflow flow and character counts;
- translated-line overlap count;
- protected-region overlap count;
- minimum font size and font scale;
- newly introduced sub-6pt flow count;
- page count, page dimensions, links, protection validation, and visual error.

M5.1 adds:

- solver status;
- candidate count and viable candidate count;
- expanded, rejected, and beam-pruned state counts;
- candidate-cap and beam-truncation markers;
- selected normal/compact candidate counts by quality tier;
- total and maximum vertical adjustment;
- page-level same-type font-scale variance;
- selected cost-vector components;
- independent final-validation status.

Runtime duration may be reported for observation but is not part of deterministic serialized
identity or a pass/fail comparison.

## 13. Testing Strategy

### 13.1 Model and Candidate Tests

- candidate IDs are stable across process runs and input mapping order;
- all font breakpoints and absolute/relative floors are included exactly once;
- vertical adjustment stays within the configured cap, page, column, and fixed-object boundaries;
- dominance pruning is deterministic;
- candidate-cap truncation is explicit;
- diagnostics contain no API key or rejected full translation text.

### 13.2 Constraint and Solver Tests

- a minimal fixture where greedy selection fails but a global combination succeeds;
- shuffled flow and candidate order produces byte-equivalent selected IDs and placements;
- normal >=90%, compact >=90%, and below-90% priorities match the approved policy;
- same-type style variance and movement break otherwise equal ties;
- protected, translated, page, column, order, and font constraints each reject a targeted fixture;
- exhaustive failure yields `REVIEW_INFEASIBLE`;
- beam or candidate-cap truncation without a solution yields `REVIEW_SEARCH_LIMIT`;
- the independent validator rejects a deliberately corrupted selected result;
- a cross-page flow uses one bound candidate without acquiring new regions.

### 13.3 Translation-Job Tests

- solved jobs render and keep existing M4.3 artifacts and security guarantees;
- review jobs write diagnostics, preserve cache, and do not create a new PDF;
- an existing valid output PDF remains byte-for-byte unchanged on a later review run and the report
  records that it was not written;
- increasing beam width reuses cached translations with zero provider calls and zero fresh billing;
- layout failures never expose paper text or credentials in error summaries.

### 13.4 PDF Regression Gates

The existing four-paper normal-length baseline and Fast R-CNN 1.3x scenario must remain green. Add
at least one deterministic synthetic PDF whose locally greedy result fails but the global solver
finds a valid combination.

For every acceptance PDF:

- page count and dimensions are unchanged;
- links and protected values remain intact;
- overflow, translated overlap, and protected overlap counts are zero for `SOLVED`;
- no new sub-6pt text appears and minimum scale is at least 0.72;
- solver status, movement, style variance, and search diagnostics are present;
- rerunning with permuted flow order produces the same selected candidate IDs and quality metrics.

## 14. Completion Gate

M5.1 is complete only when:

- the deterministic global solver is the default CJK layout path;
- no automatic greedy fallback exists;
- all M4.3 provider, protection, cache, usage, cost, and privacy tests pass unchanged;
- all unit, integration, full-PDF, and permutation-invariance tests pass;
- the four-paper and 1.3x baselines pass without overflow, overlap, page-count change, or new sub-6pt
  text;
- review outcomes never create or replace an incomplete PDF;
- `README.md`, `docs/BUILD_FLOW.md`, and `AGENTS.md` describe the same milestone state and remaining
  limitations.

OCR, external model downloads, GUI work, Google Translate, terminology/context enhancement, and a
specialized optimization library remain outside the M5.1 completion gate.

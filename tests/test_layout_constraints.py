import json

from papertrans.domain import BoundingBox, Document, Page, Region, RegionType, TextFlow
from papertrans.layout import DocumentLayout, FlowLayout, LinePlacement, validate_layout
from papertrans.layout.constraints import boxes_overlap


def _document(*, overlap_regions: bool = False, protected_overlap: bool = False) -> Document:
    first = Region(
        id="region-a",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(40, 40, 160, 90),
        reading_order=1,
    )
    second = Region(
        id="region-b",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(40, 40 if overlap_regions else 100, 160, 90 if overlap_regions else 150),
        reading_order=2,
    )
    formula = Region(
        id="formula",
        type=RegionType.FORMULA,
        bbox=BoundingBox(
            40,
            40 if protected_overlap else 160,
            160,
            60 if protected_overlap else 180,
        ),
        translatable=False,
    )
    return Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=200, height=200, regions=[first, second, formula])],
        text_flows=[
            TextFlow("flow-a", RegionType.PARAGRAPH, ["region-a"], [1], "a", "a", True),
            TextFlow("flow-b", RegionType.PARAGRAPH, ["region-b"], [1], "b", "b", True),
        ],
    )


def _flow_layout(
    flow_id: str,
    *,
    region_id: str | None = None,
    baseline: float | None = None,
    font_size: float = 10.0,
    fit: bool = True,
    overflow_text: str = "",
) -> FlowLayout:
    bound_region = region_id or ("region-a" if flow_id == "flow-a" else "region-b")
    default_baseline = 50.0 if bound_region == "region-a" else 110.0
    return FlowLayout(
        flow_id=flow_id,
        region_ids=[bound_region],
        variant="normal",
        original_font_size=10.0,
        font_size=font_size,
        fit=fit,
        overflow_text=overflow_text,
        placements=[
            LinePlacement(
                flow_id=flow_id,
                region_id=bound_region,
                page_number=1,
                text="private fixture translation",
                x=40,
                baseline_y=default_baseline if baseline is None else baseline,
                font_size=font_size,
                bold=False,
                color=0,
            )
        ],
    )


def _layout(*flows: FlowLayout) -> DocumentLayout:
    return DocumentLayout("font.ttf", "bold.ttf", list(flows), {})


def test_boxes_touching_at_edge_need_clearance_to_overlap() -> None:
    assert boxes_overlap((0, 0, 10, 10), (10, 0, 20, 10)) is False
    assert boxes_overlap((0, 0, 10, 10), (10, 0, 20, 10), clearance=0.25) is True


def test_valid_layout_passes_independent_validation() -> None:
    report = validate_layout(_document(), _layout(_flow_layout("flow-a"), _flow_layout("flow-b")))

    assert report.passed is True
    assert report.violations == ()


def test_selection_reason_codes_cover_missing_duplicate_and_unexpected_flows() -> None:
    report = validate_layout(
        _document(),
        _layout(_flow_layout("flow-a"), _flow_layout("flow-a"), _flow_layout("flow-c")),
    )

    assert {"missing_flow", "duplicate_flow", "unexpected_flow"} <= set(report.violations)


def test_layout_reports_overflow_and_font_floor() -> None:
    report = validate_layout(
        _document(),
        _layout(
            _flow_layout("flow-a", fit=False, overflow_text="not persisted"),
            _flow_layout("flow-b", font_size=5.5),
        ),
    )

    assert {"overflow", "font_floor"} <= set(report.violations)


def test_layout_reports_region_binding_and_page_bounds() -> None:
    wrong_binding = _flow_layout("flow-a", region_id="region-b")
    wrong_binding.region_ids = ["region-a"]
    report = validate_layout(
        _document(),
        _layout(wrong_binding, _flow_layout("flow-b", baseline=0.0)),
    )

    assert {"region_binding", "page_bounds"} <= set(report.violations)


def test_layout_reports_translated_and_protected_overlap() -> None:
    report = validate_layout(
        _document(overlap_regions=True, protected_overlap=True),
        _layout(_flow_layout("flow-a"), _flow_layout("flow-b", baseline=50.0)),
    )

    assert {"translated_overlap", "protected_overlap"} <= set(report.violations)


def test_safety_report_never_serializes_translation_text() -> None:
    report = validate_layout(
        _document(),
        _layout(
            _flow_layout("flow-a", fit=False, overflow_text="secret overflow text"),
            _flow_layout("flow-b"),
        ),
    )

    payload = json.dumps(report.to_dict())
    assert "private fixture translation" not in payload
    assert "secret overflow text" not in payload
    assert report.to_dict()["violations"] == ["overflow"]

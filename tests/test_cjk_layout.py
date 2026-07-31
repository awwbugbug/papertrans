from papertrans.domain import (
    BoundingBox,
    Document,
    Page,
    Region,
    RegionType,
    TextFlow,
    TextStyle,
)
from papertrans.layout import build_cjk_layout
from papertrans.translation import TranslationResult


def _document_with_flow(width: float = 220, height: float = 120) -> Document:
    region = Region(
        id="p1-text-1",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(50, 100, 50 + width, 100 + height),
        source_text="Source paragraph text.",
        style=TextStyle(font_name="Times", font_size=10, color=0),
        reading_order=1,
    )
    flow = TextFlow(
        id="flow-p1-text-1",
        type=RegionType.PARAGRAPH,
        region_ids=[region.id],
        page_numbers=[1],
        raw_text=region.source_text,
        source_text=region.source_text,
        translatable=True,
    )
    return Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=600, height=800, regions=[region])],
        text_flows=[flow],
    )


def test_cjk_layout_fits_translation_and_maps_lines_to_region() -> None:
    document = _document_with_flow()
    translation = TranslationResult(
        segment_id="flow-p1-text-1",
        normal="这是用于验证中文换行和文本区域映射的模拟内容。" * 2,
        compact="这是用于验证中文换行的紧凑内容。",
        provider="mock",
    )

    layout = build_cjk_layout(document, {translation.segment_id: translation})

    assert layout.stats["overflow_flow_count"] == 0
    assert layout.flows[0].fit is True
    assert layout.flows[0].placements
    assert all(line.region_id == "p1-text-1" for line in layout.flows[0].placements)


def test_cjk_layout_reports_overflow_for_impossibly_small_box() -> None:
    document = _document_with_flow(width=20, height=8)
    translation = TranslationResult(
        segment_id="flow-p1-text-1",
        normal="无法放下的模拟中文内容" * 20,
        compact="仍然无法放下" * 10,
        provider="mock",
    )

    layout = build_cjk_layout(document, {translation.segment_id: translation})

    assert layout.stats["overflow_flow_count"] == 1
    assert layout.flows[0].fit is False
    assert layout.flows[0].overflow_text


def test_cjk_layout_skips_slots_occupied_by_formula_and_other_flows() -> None:
    first = Region(
        id="p1-text-1",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(50, 100, 270, 180),
        source_text="First source paragraph.",
        style=TextStyle(font_name="Times", font_size=10, color=0),
        reading_order=1,
    )
    formula = Region(
        id="p1-formula-1",
        type=RegionType.FORMULA,
        bbox=BoundingBox(140, 150, 260, 172),
        source_text="L(p) = x + y",
        translatable=False,
        reading_order=None,
    )
    second = Region(
        id="p1-text-2",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(50, 160, 270, 290),
        source_text="Second source paragraph.",
        style=TextStyle(font_name="Times", font_size=10, color=0),
        reading_order=2,
    )
    flows = [
        TextFlow(
            id="flow-p1-text-1",
            type=RegionType.PARAGRAPH,
            region_ids=[first.id],
            page_numbers=[1],
            raw_text=first.source_text,
            source_text=first.source_text,
            translatable=True,
        ),
        TextFlow(
            id="flow-p1-text-2",
            type=RegionType.PARAGRAPH,
            region_ids=[second.id],
            page_numbers=[1],
            raw_text=second.source_text,
            source_text=second.source_text,
            translatable=True,
        ),
    ]
    document = Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=600, height=800, regions=[first, formula, second])],
        text_flows=flows,
    )
    translations = {
        flow.id: TranslationResult(
            segment_id=flow.id,
            normal="这是用于验证页面级碰撞检测的模拟中文内容。" * 3,
            compact="这是用于验证碰撞检测的紧凑中文。" * 2,
            provider="mock",
        )
        for flow in flows
    }

    layout = build_cjk_layout(document, translations)

    assert all(flow.fit for flow in layout.flows)
    assert layout.stats["blocked_line_slot_count"] > 0
    assert layout.stats["translated_line_overlap_count"] == 0
    assert layout.stats["protected_region_overlap_count"] == 0

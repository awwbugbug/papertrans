from papertrans.domain import BoundingBox, Document, Page, Region, RegionType, TextStyle
from papertrans.structure.text_flow import build_text_flows, normalize_fragments


def _paragraph(
    region_id: str,
    text: str,
    bbox: tuple[float, float, float, float],
    order: int,
    column: int,
    font_size: float = 10,
) -> Region:
    return Region(
        id=region_id,
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(*bbox),
        source_text=text,
        style=TextStyle(font_name="Test", font_size=font_size),
        reading_order=order,
        metadata={"column_index": column},
    )


def _ocr_line(
    region_id: str,
    text: str,
    bbox: tuple[float, float, float, float],
    order: int,
    column: int = 0,
) -> Region:
    region = _paragraph(region_id, text, bbox, order, column, font_size=8)
    region.confidence = 0.96
    region.metadata.update(
        {"content_source": "paddleocr", "content_confidence": 0.96}
    )
    return region


def test_normalize_fragments_records_dehyphenation_decisions() -> None:
    text, decisions = normalize_fragments(
        ["The model is im-", "proved and state-", "of-the-art."],
    )

    assert text == "The model is improved and state-of-the-art."
    assert [decision["action"] for decision in decisions] == ["remove", "preserve"]


def test_cross_column_continuation_creates_one_traceable_flow() -> None:
    previous = _paragraph(
        "left-last",
        "The scientific paragraph continues smoothly",
        (50, 620, 280, 760),
        order=1,
        column=1,
    )
    following = _paragraph(
        "right-first",
        "across the next column.",
        (320, 80, 550, 220),
        order=2,
        column=2,
    )
    document = Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=600, height=800, regions=[previous, following])],
    )

    flows = build_text_flows(document)

    assert len(flows) == 1
    assert flows[0].region_ids == ["left-last", "right-first"]
    assert flows[0].source_text == (
        "The scientific paragraph continues smoothly across the next column."
    )
    assert flows[0].metadata["continuity_edges"][0]["boundary"] == "cross_column"
    assert previous.metadata["text_flow_id"] == flows[0].id
    assert following.metadata["text_flow_id"] == flows[0].id


def test_font_mismatch_prevents_table_text_from_merging() -> None:
    previous = _paragraph(
        "body",
        "The paragraph continues",
        (50, 620, 280, 760),
        order=1,
        column=1,
    )
    table_like = _paragraph(
        "table-row",
        "method score accuracy",
        (320, 80, 550, 120),
        order=2,
        column=2,
        font_size=7,
    )
    document = Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=600, height=800, regions=[previous, table_like])],
    )

    flows = build_text_flows(document)

    assert len(flows) == 2


def test_cross_page_continuation_preserves_page_and_region_mapping() -> None:
    previous = _paragraph(
        "page-one-last",
        "The scientific explanation continues naturally",
        (320, 620, 550, 760),
        order=1,
        column=2,
    )
    following = _paragraph(
        "page-two-first",
        "on the following page without interruption.",
        (50, 80, 280, 220),
        order=1,
        column=1,
    )
    document = Document(
        source_path="fixture.pdf",
        pages=[
            Page(number=1, width=600, height=800, regions=[previous]),
            Page(number=2, width=600, height=800, regions=[following]),
        ],
    )

    flows = build_text_flows(document)

    assert len(flows) == 1
    assert flows[0].page_numbers == [1, 2]
    assert flows[0].region_ids == ["page-one-last", "page-two-first"]
    assert flows[0].metadata["continuity_edges"][0]["boundary"] == "cross_page"


def test_numeric_paragraph_continuations_merge_into_one_flow() -> None:
    regions = [
        _paragraph(
            "schedule",
            "We continue training with a learning rate of 10−2",
            (50, 400, 280, 460),
            order=1,
            column=1,
        ),
        _paragraph(
            "epochs",
            "for 75 epochs, then 10−3 for 30 epochs, and finally 10−4",
            (50, 459, 280, 473),
            order=2,
            column=1,
        ),
        _paragraph(
            "ending",
            "for 30 epochs.",
            (50, 475, 110, 486),
            order=3,
            column=1,
        ),
    ]
    document = Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=600, height=800, regions=regions)],
    )

    flows = build_text_flows(document)

    assert len(flows) == 1
    assert flows[0].region_ids == ["schedule", "epochs", "ending"]


def test_ocr_lines_merge_by_geometry_even_when_a_line_ends_with_period() -> None:
    lines = [
        _ocr_line(
            "line-1",
            "The first sentence ends here.",
            (50, 80, 330, 90),
            order=1,
        ),
        _ocr_line(
            "line-2",
            "The same paragraph continues on the next physical line",
            (50, 94, 350, 104),
            order=2,
        ),
        _ocr_line(
            "line-3",
            "and finishes with a shorter final line.",
            (50, 108, 245, 118),
            order=3,
        ),
    ]
    document = Document(
        source_path="scan.pdf",
        pages=[Page(number=1, width=400, height=600, regions=lines)],
    )

    flows = build_text_flows(document)

    assert len(flows) == 1
    assert flows[0].region_ids == ["line-1", "line-2", "line-3"]
    assert [
        edge["boundary"] for edge in flows[0].metadata["continuity_edges"]
    ] == ["ocr_same_paragraph", "ocr_same_paragraph"]
    assert document.metadata["text_flow_stats"]["ocr_line_edges"] == 2


def test_ocr_geometry_keeps_paragraph_gap_and_column_boundary_separate() -> None:
    lines = [
        _ocr_line(
            "paragraph-one-final",
            "This is the short final line.",
            (50, 80, 210, 90),
            order=1,
        ),
        _ocr_line(
            "paragraph-two-first",
            "A new indented paragraph begins after a visible gap.",
            (60, 108, 350, 118),
            order=2,
        ),
        _ocr_line(
            "right-column",
            "This belongs to another column.",
            (220, 80, 380, 90),
            order=3,
            column=2,
        ),
    ]
    document = Document(
        source_path="scan.pdf",
        pages=[Page(number=1, width=400, height=600, regions=lines)],
    )

    flows = build_text_flows(document)

    assert len(flows) == 3
    assert all(len(flow.region_ids) == 1 for flow in flows)

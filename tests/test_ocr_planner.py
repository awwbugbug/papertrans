from papertrans.domain import BoundingBox, Document, Page, Region, RegionType
from papertrans.ingest import OCRAction, build_ocr_plan


def _text_region(region_id: str, text: str) -> Region:
    return Region(
        id=region_id,
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(40, 40, 360, 240),
        source_text=text,
        metadata={"content_source": "native_pdf", "content_confidence": 1.0},
    )


def _image_region(region_id: str, bbox: BoundingBox) -> Region:
    return Region(
        id=region_id,
        type=RegionType.FIGURE,
        bbox=bbox,
        translatable=False,
        metadata={"native_block_type": "image"},
    )


def test_planner_keeps_reliable_native_text_and_routes_scan_pages() -> None:
    native = Page(
        number=1,
        width=400,
        height=600,
        regions=[_text_region("native", "A" * 120)],
    )
    scanned = Page(
        number=2,
        width=400,
        height=600,
        regions=[_image_region("scan", BoundingBox(0, 0, 400, 600))],
    )

    plan = build_ocr_plan(Document(source_path="fixture.pdf", pages=[native, scanned]))

    assert plan.pages[0].action is OCRAction.KEEP_NATIVE
    assert plan.pages[1].action is OCRAction.RUN_OCR
    assert plan.pages[1].diagnostics.raster_image_coverage_ratio == 1.0
    assert plan.blocking_page_numbers == (2,)
    assert plan.to_dict()["summary"] == {
        "page_count": 2,
        "keep_native_count": 1,
        "run_ocr_count": 1,
        "use_ocr_count": 0,
        "review_count": 0,
        "skip_blank_count": 0,
        "blocking_page_count": 1,
    }


def test_planner_reviews_ambiguous_pages_and_skips_only_true_blanks() -> None:
    mixed = Page(
        number=1,
        width=400,
        height=600,
        regions=[
            _image_region("scan", BoundingBox(0, 0, 400, 600)),
            _text_region("overlay", "native overlay with uncertain completeness"),
        ],
    )
    vector_only = Page(
        number=2,
        width=400,
        height=600,
        metadata={"native_drawing_count": 3},
    )
    blank = Page(number=3, width=400, height=600)

    plan = build_ocr_plan(
        Document(source_path="fixture.pdf", pages=[mixed, vector_only, blank])
    )

    assert [page.action for page in plan.pages] == [
        OCRAction.REVIEW,
        OCRAction.REVIEW,
        OCRAction.SKIP_BLANK,
    ]
    assert plan.pages[0].reason_codes == ("sparse_text_over_large_raster",)
    assert plan.pages[1].reason_codes == ("vector_content_without_native_text",)


def test_planner_reviews_suspicious_native_text_without_scan_evidence() -> None:
    page = Page(
        number=1,
        width=400,
        height=600,
        regions=[_text_region("bad-font", "\ue000" * 120)],
    )

    plan = build_ocr_plan(Document(source_path="fixture.pdf", pages=[page]))

    assert plan.pages[0].action is OCRAction.REVIEW
    assert plan.pages[0].reason_codes == ("unreliable_native_text",)
    assert plan.pages[0].diagnostics.native_text_quality_ratio == 0.0


def test_planner_keeps_sparse_valid_native_text_without_scan_evidence() -> None:
    page = Page(
        number=1,
        width=400,
        height=600,
        regions=[_text_region("divider", "Appendix")],
    )

    plan = build_ocr_plan(Document(source_path="fixture.pdf", pages=[page]))

    assert plan.pages[0].action is OCRAction.KEEP_NATIVE
    assert plan.pages[0].reason_codes == ("sparse_native_text_without_scan_evidence",)


def test_planner_uses_union_raster_coverage_without_double_counting() -> None:
    page = Page(
        number=1,
        width=400,
        height=600,
        regions=[
            _image_region("left", BoundingBox(0, 0, 240, 600)),
            _image_region("overlap", BoundingBox(160, 0, 400, 600)),
        ],
    )

    plan = build_ocr_plan(Document(source_path="fixture.pdf", pages=[page]))

    assert plan.pages[0].diagnostics.raster_image_coverage_ratio == 1.0
    assert plan.pages[0].action is OCRAction.RUN_OCR


def test_planner_accepts_confident_fused_ocr_without_counting_it_as_native() -> None:
    page = Page(
        number=1,
        width=400,
        height=600,
        regions=[
            _image_region("scan", BoundingBox(0, 0, 400, 600)),
            Region(
                id="ocr-line",
                type=RegionType.PARAGRAPH,
                bbox=BoundingBox(40, 80, 360, 100),
                source_text="Recognized academic text " * 5,
                confidence=0.96,
                metadata={"content_source": "paddleocr"},
            ),
        ],
    )

    plan = build_ocr_plan(Document(source_path="fixture.pdf", pages=[page]))

    assert plan.pages[0].action is OCRAction.USE_OCR
    assert plan.pages[0].diagnostics.native_character_count == 0
    assert plan.pages[0].diagnostics.ocr_character_count > 80
    assert plan.blocking_page_numbers == ()

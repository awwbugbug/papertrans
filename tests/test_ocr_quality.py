from papertrans.domain import BoundingBox, Document, Page, Region, RegionType
from papertrans.qa import OCRQualityPolicy, evaluate_ocr_documents


def _document(text: str) -> Document:
    return Document(
        source_path="fixture.pdf",
        pages=[
            Page(
                number=1,
                width=400,
                height=600,
                regions=[
                    Region(
                        id="text",
                        type=RegionType.PARAGRAPH,
                        bbox=BoundingBox(40, 80, 360, 120),
                        source_text=text,
                        reading_order=1,
                    )
                ],
            )
        ],
    )


def test_ocr_quality_reports_cer_order_and_coverage_without_text() -> None:
    report = evaluate_ocr_documents(
        _document("The model detects objects accurately in every evaluation image."),
        _document("The model detects object accurately in every evaluation image."),
    )

    assert 0 < report["summary"]["character_error_rate"] < 0.1
    assert 0.8 < report["summary"]["token_order_similarity"] < 1.0
    assert 0.9 < report["summary"]["character_coverage_ratio"] <= 1.0
    assert "text" not in str(report).lower()
    assert report["passed"] is True


def test_ocr_quality_fails_closed_for_large_recognition_loss() -> None:
    report = evaluate_ocr_documents(
        _document("A complete academic paragraph with important evidence."),
        _document("academic evidence"),
        policy=OCRQualityPolicy(max_character_error_rate=0.1),
    )

    assert report["passed"] is False
    assert "character_error_rate" in report["violations"]
    assert "character_coverage" in report["violations"]

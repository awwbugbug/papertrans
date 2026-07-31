from pathlib import Path

import pymupdf

from papertrans.domain import BoundingBox
from papertrans.ingest import OCRAction, OCRLine, OCRRuntimeConfig, prepare_document
from papertrans.ingest.ocr_execution import _resolve_model_directory


class FakeOCRBackend:
    name = "fake-ocr"

    def __init__(self) -> None:
        self.page_numbers: list[int] = []

    def recognize(self, page):  # type: ignore[no-untyped-def]
        self.page_numbers.append(page.page_number)
        return (
            OCRLine(
                text="Recognized academic paragraph " * 5,
                polygon=((40, 80), (360, 80), (360, 104), (40, 104)),
                confidence=0.97,
            ),
        )


def _create_mixed_fixture(path: Path) -> None:
    document = pymupdf.open()
    native = document.new_page(width=400, height=600)
    native.insert_textbox(
        pymupdf.Rect(40, 80, 360, 300),
        "Native academic paragraph with a reliable text layer. " * 5,
        fontsize=10,
    )
    raster_source = pymupdf.open()
    raster_page = raster_source.new_page(width=400, height=600)
    raster_page.insert_textbox(
        pymupdf.Rect(40, 80, 360, 300),
        "Raster academic paragraph without a native text layer. " * 5,
        fontsize=10,
    )
    image = raster_page.get_pixmap(alpha=False).tobytes("png")
    raster_source.close()
    scanned = document.new_page(width=400, height=600)
    scanned.insert_image(scanned.rect, stream=image)
    document.save(path)
    document.close()


def test_prepare_document_runs_ocr_only_for_scan_candidates(tmp_path: Path) -> None:
    source = tmp_path / "mixed.pdf"
    _create_mixed_fixture(source)
    backend = FakeOCRBackend()

    result = prepare_document(
        source,
        OCRRuntimeConfig(backend="paddleocr", model_dir=tmp_path, dpi=72),
        backend=backend,
    )

    assert backend.page_numbers == [2]
    assert [page.action for page in result.plan.pages] == [
        OCRAction.KEEP_NATIVE,
        OCRAction.USE_OCR,
    ]
    ocr_regions = [
        region
        for region in result.document.pages[1].regions
        if region.metadata.get("content_source") == "paddleocr"
    ]
    assert len(ocr_regions) == 1
    assert ocr_regions[0].bbox == BoundingBox(40, 80, 360, 104)
    assert result.run.to_dict()["recognized_page_count"] == 1
    assert result.run.to_dict()["recognized_line_count"] == 1
    background = next(
        region
        for region in result.document.pages[1].regions
        if region.metadata.get("native_block_type") == "image"
    )
    assert background.metadata["ocr_background"] is True


def test_model_resolver_accepts_extra_recognition_directory_layer(tmp_path: Path) -> None:
    model = tmp_path / "PP-OCRv6_medium_rec_infer" / "PP-OCRv6_medium_rec_infer"
    model.mkdir(parents=True)
    (model / "inference.json").write_text("{}", encoding="utf-8")
    (model / "inference.pdiparams").write_bytes(b"fixture")

    assert _resolve_model_directory(tmp_path, "PP-OCRv6_medium_rec_infer") == model

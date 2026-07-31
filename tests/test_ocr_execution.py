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


class ScriptedRegionOCRBackend:
    name = "fake-ocr"

    def __init__(self, lines):  # type: ignore[no-untyped-def]
        self.lines = lines
        self.rendered = []

    def recognize(self, page):  # type: ignore[no-untyped-def]
        self.rendered.append(page)
        return tuple(self.lines)


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


def _create_embedded_image_fixture(path: Path, *, native_overlap: bool = False) -> None:
    raster_source = pymupdf.open()
    raster_page = raster_source.new_page(width=300, height=220)
    raster_page.insert_textbox(
        pymupdf.Rect(15, 20, 285, 205),
        "Embedded raster paragraph for selective OCR. " * 8,
        fontsize=10,
    )
    image = raster_page.get_pixmap(alpha=False).tobytes("png")
    raster_source.close()

    document = pymupdf.open()
    page = document.new_page(width=400, height=600)
    page.insert_textbox(
        pymupdf.Rect(40, 40, 360, 180),
        "Reliable native academic paragraph above the embedded image. " * 5,
        fontsize=10,
    )
    page.insert_image(pymupdf.Rect(50, 260, 350, 480), stream=image)
    page.insert_textbox(
        pymupdf.Rect(50, 490, 350, 520),
        "Figure 1. Embedded raster excerpt.",
        fontsize=9,
    )
    if native_overlap:
        page.insert_textbox(
            pymupdf.Rect(65, 280, 335, 310),
            "Duplicate native overlay text " * 4,
            fontsize=9,
        )
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


def test_prepare_document_fuses_text_heavy_embedded_image_with_pdf_offset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "embedded.pdf"
    _create_embedded_image_fixture(source)
    backend = ScriptedRegionOCRBackend(
        [
            OCRLine(
                text="Recovered embedded academic paragraph line " * 2,
                polygon=((15, 20 + index * 28), (285, 20 + index * 28),
                         (285, 30 + index * 28), (15, 30 + index * 28)),
                confidence=0.96,
            )
            for index in range(3)
        ]
    )

    result = prepare_document(
        source,
        OCRRuntimeConfig(backend="paddleocr", model_dir=tmp_path, dpi=72),
        backend=backend,
    )

    assert result.plan.pages[0].action is OCRAction.USE_MIXED
    assert len(backend.rendered) == 1
    assert backend.rendered[0].clip_bbox == BoundingBox(50, 260, 350, 480)
    ocr_regions = [
        region
        for region in result.document.pages[0].regions
        if region.metadata.get("content_source") == "paddleocr"
    ]
    assert len(ocr_regions) == 3
    assert all(region.translatable for region in ocr_regions)
    assert ocr_regions[0].bbox.x0 == 65
    assert ocr_regions[0].bbox.y0 == 280
    image_region = next(
        region
        for region in result.document.pages[0].regions
        if region.metadata.get("native_block_type") == "image"
    )
    assert image_region.metadata["ocr_background"] is True
    assert result.run.to_dict()["recognized_region_count"] == 1


def test_prepare_document_discards_region_ocr_that_duplicates_native_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "duplicate.pdf"
    _create_embedded_image_fixture(source, native_overlap=True)
    duplicate = OCRLine(
        text="Duplicate native overlay text " * 4,
        polygon=((15, 20), (285, 20), (285, 50), (15, 50)),
        confidence=0.98,
    )
    backend = ScriptedRegionOCRBackend([duplicate, duplicate, duplicate])

    result = prepare_document(
        source,
        OCRRuntimeConfig(backend="paddleocr", model_dir=tmp_path, dpi=72),
        backend=backend,
    )

    assert result.plan.pages[0].action is OCRAction.KEEP_NATIVE
    assert result.run.to_dict()["duplicate_line_count"] == 3
    assert result.run.to_dict()["recognized_region_count"] == 0


def test_prepare_document_ignores_sparse_ocr_labels_in_ordinary_figure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sparse.pdf"
    _create_embedded_image_fixture(source)
    backend = ScriptedRegionOCRBackend(
        [
            OCRLine(
                text="Accuracy",
                polygon=((20, 20), (90, 20), (90, 40), (20, 40)),
                confidence=0.97,
            ),
            OCRLine(
                text="Epoch",
                polygon=((180, 180), (240, 180), (240, 200), (180, 200)),
                confidence=0.95,
            ),
        ]
    )

    result = prepare_document(
        source,
        OCRRuntimeConfig(backend="paddleocr", model_dir=tmp_path, dpi=72),
        backend=backend,
    )

    assert result.plan.pages[0].action is OCRAction.KEEP_NATIVE
    assert result.run.to_dict()["ignored_region_count"] == 1
    image_region = next(
        region
        for region in result.document.pages[0].regions
        if region.metadata.get("native_block_type") == "image"
    )
    assert "ocr_background" not in image_region.metadata

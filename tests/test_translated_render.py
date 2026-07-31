from papertrans.domain import BoundingBox, Page, Region, RegionType
from papertrans.render.translated import _redaction_boxes, _source_redaction_box


def _intersection_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    return width * height


def test_redaction_boxes_preserve_protected_formula_cutout() -> None:
    source = (50.0, 100.0, 270.0, 200.0)
    formula = (140.0, 145.0, 260.0, 170.0)

    boxes, cutouts = _redaction_boxes(source, [formula])

    assert cutouts == 1
    assert len(boxes) == 4
    assert all(_intersection_area(box, formula) == 0 for box in boxes)
    assert sum((box[2] - box[0]) * (box[3] - box[1]) for box in boxes) == 19000.0


def test_ocr_redaction_expands_slightly_without_changing_native_boxes() -> None:
    page = Page(number=1, width=400, height=600)
    ocr = Region(
        id="ocr",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(40, 80, 360, 100),
        metadata={"content_source": "paddleocr"},
    )
    native = Region(
        id="native",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(40, 80, 360, 100),
        metadata={"content_source": "native_pdf"},
    )

    assert _source_redaction_box(ocr, page) == (38.0, 78.75, 362.0, 101.25)
    assert _source_redaction_box(native, page) == (40.0, 80.0, 360.0, 100.0)

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

import pymupdf

from papertrans.domain import BoundingBox, Document, Page, Region, RegionType, TextStyle
from papertrans.structure import recover_document_structure


def _all_span_sizes(blocks: list[dict[str, Any]]) -> list[float]:
    sizes: list[float] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                size = span.get("size")
                if isinstance(size, (int, float)) and size > 0:
                    sizes.append(float(size))
    return sizes


def _block_text_and_style(
    block: dict[str, Any],
) -> tuple[str, TextStyle | None, float, list[dict[str, Any]]]:
    lines: list[str] = []
    spans: list[dict[str, Any]] = []
    native_lines: list[dict[str, Any]] = []
    for line in block.get("lines", []):
        line_spans = line.get("spans", [])
        spans.extend(line_spans)
        text = "".join(str(span.get("text", "")) for span in line_spans).strip()
        if text:
            lines.append(text)
        native_lines.append(
            {
                "bbox": [round(float(value), 3) for value in line.get("bbox", [])],
                "direction": [round(float(value), 5) for value in line.get("dir", (1, 0))],
                "spans": [
                    {
                        "text": str(span.get("text", "")),
                        "bbox": [round(float(value), 3) for value in span.get("bbox", [])],
                        "origin": [round(float(value), 3) for value in span.get("origin", ())],
                        "font": str(span.get("font", "")),
                        "size": round(float(span.get("size", 0.0)), 3),
                        "color": int(span.get("color", 0)),
                        "flags": int(span.get("flags", 0)),
                    }
                    for span in line_spans
                ],
            }
        )

    if not spans:
        return "\n".join(lines), None, 0.0, native_lines

    dominant = max(spans, key=lambda span: len(str(span.get("text", ""))))
    max_size = max(float(span.get("size", 0.0)) for span in spans)
    style = TextStyle(
        font_name=str(dominant.get("font")) if dominant.get("font") else None,
        font_size=float(dominant.get("size")) if dominant.get("size") else None,
        color=int(dominant.get("color")) if dominant.get("color") is not None else None,
        flags=int(dominant.get("flags", 0)),
    )
    return "\n".join(lines), style, max_size, native_lines


def _classify_text_region(
    text: str,
    bbox: BoundingBox,
    page_height: float,
    block_max_size: float,
    body_size: float,
) -> RegionType:
    normalized = text.strip()
    if normalized.isdigit() and bbox.y0 >= page_height * 0.82:
        return RegionType.PAGE_NUMBER
    if bbox.y1 <= page_height * 0.08:
        return RegionType.HEADER
    if bbox.y0 >= page_height * 0.92:
        return RegionType.FOOTER
    if body_size > 0 and block_max_size >= body_size * 1.35 and bbox.y0 <= page_height * 0.45:
        return RegionType.TITLE
    if body_size > 0 and block_max_size >= body_size * 1.15:
        return RegionType.HEADING
    return RegionType.PARAGRAPH


def extract_document(source: str | Path) -> Document:
    """Extract an initial, inspectable document model from a born-digital PDF.

    This is deliberately a baseline extractor. Reading-order recovery, formula detection,
    paragraph merging, and OCR fusion belong to later pipeline stages.
    """

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF not found: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {source_path.suffix or '<no extension>'}")

    result = Document(source_path=str(source_path))
    with pymupdf.open(source_path) as pdf:
        result.metadata = {
            "page_count": pdf.page_count,
            "pdf_metadata": {key: value for key, value in pdf.metadata.items() if value},
            "extractor": "pymupdf-native",
        }

        for page_index, pdf_page in enumerate(pdf):
            raw = pdf_page.get_text("dict", sort=True)
            blocks = list(raw.get("blocks", []))
            span_sizes = _all_span_sizes(blocks)
            body_size = median(span_sizes) if span_sizes else 0.0
            page = Page(
                number=page_index + 1,
                width=float(pdf_page.rect.width),
                height=float(pdf_page.rect.height),
                metadata={
                    "native_drawing_count": len(pdf_page.get_drawings()),
                    "native_link_count": len(pdf_page.get_links()),
                },
            )

            for block_index, block in enumerate(blocks):
                bbox_values = block.get("bbox")
                if not bbox_values or len(bbox_values) != 4:
                    continue
                bbox = BoundingBox(*(float(value) for value in bbox_values))
                block_type = int(block.get("type", -1))

                if block_type == 1:
                    page.regions.append(
                        Region(
                            id=f"p{page.number}-image-{block_index}",
                            type=RegionType.FIGURE,
                            bbox=bbox,
                            translatable=False,
                            metadata={
                                "native_block_type": "image",
                                "content_source": "native_pdf_image",
                                "content_confidence": 1.0,
                            },
                        )
                    )
                    continue
                if block_type != 0:
                    continue

                text, style, block_max_size, native_lines = _block_text_and_style(block)
                if not text.strip():
                    continue
                region_type = _classify_text_region(
                    text=text,
                    bbox=bbox,
                    page_height=page.height,
                    block_max_size=block_max_size,
                    body_size=body_size,
                )
                page.regions.append(
                    Region(
                        id=f"p{page.number}-text-{block_index}",
                        type=region_type,
                        bbox=bbox,
                        source_text=text,
                        style=style,
                        reading_order=None,
                        translatable=region_type
                        not in {RegionType.HEADER, RegionType.FOOTER, RegionType.PAGE_NUMBER},
                        confidence=0.6,
                        metadata={
                            "native_block_type": "text",
                            "content_source": "native_pdf",
                            "content_confidence": 1.0,
                            "baseline_classifier": True,
                            "max_font_size": round(block_max_size, 3),
                            "native_lines": native_lines,
                        },
                    )
                )

            result.pages.append(page)

    return recover_document_structure(result)

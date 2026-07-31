from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

from papertrans.domain import Document
from papertrans.layout import DocumentLayout
from papertrans.layout.cjk_font import CJKFontResolver


@dataclass(frozen=True, slots=True)
class TranslatedRenderStats:
    redacted_regions: int
    redaction_rectangles: int
    protected_cutouts: int
    rendered_lines: int
    restored_links: int
    fonts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "redacted_regions": self.redacted_regions,
            "redaction_rectangles": self.redaction_rectangles,
            "protected_cutouts": self.protected_cutouts,
            "rendered_lines": self.rendered_lines,
            "restored_links": self.restored_links,
            "fonts": self.fonts,
            "renderer": "cjk_textflow_white_redaction_v1",
        }


def _rgb(color: int) -> tuple[float, float, float]:
    red, green, blue = pymupdf.sRGB_to_rgb(color)
    return red / 255, green / 255, blue / 255


def _subtract_box(
    source: tuple[float, float, float, float],
    blocker: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    x0 = max(source[0], blocker[0])
    y0 = max(source[1], blocker[1])
    x1 = min(source[2], blocker[2])
    y1 = min(source[3], blocker[3])
    if x1 <= x0 or y1 <= y0:
        return [source]
    pieces = [
        (source[0], source[1], source[2], y0),
        (source[0], y1, source[2], source[3]),
        (source[0], y0, x0, y1),
        (x1, y0, source[2], y1),
    ]
    return [piece for piece in pieces if piece[2] - piece[0] > 0.25 and piece[3] - piece[1] > 0.25]


def _redaction_boxes(
    source: tuple[float, float, float, float],
    protected: list[tuple[float, float, float, float]],
) -> tuple[list[tuple[float, float, float, float]], int]:
    pieces = [source]
    cutouts = 0
    for blocker in protected:
        before = pieces
        pieces = [piece for current in pieces for piece in _subtract_box(current, blocker)]
        if pieces != before:
            cutouts += 1
    return pieces, cutouts


def render_translated_layout(
    source_path: str | Path,
    document: Document,
    layout: DocumentLayout,
    output_path: str | Path,
    font_resolver: CJKFontResolver | None = None,
) -> TranslatedRenderStats:
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolver = font_resolver or CJKFontResolver()
    region_by_id = {region.id: region for page in document.pages for region in page.regions}
    region_ids = {
        region_id
        for flow in layout.flows
        for region_id in flow.region_ids
        if region_id in region_by_id
    }
    lines_by_page: dict[int, list[Any]] = {}
    for flow in layout.flows:
        for placement in flow.placements:
            lines_by_page.setdefault(placement.page_number, []).append(placement)

    rendered_lines = 0
    restored_links = 0
    redaction_rectangles = 0
    protected_cutouts = 0
    font_counts: Counter[str] = Counter()
    with pymupdf.open(source_path) as source_pdf:
        output_pdf = pymupdf.open()
        output_pdf.insert_pdf(source_pdf, links=True, annots=True, widgets=True)
        if source_pdf.metadata:
            output_pdf.set_metadata(source_pdf.metadata)

        for page_index, page_model in enumerate(document.pages):
            output_page = output_pdf[page_index]
            source_links = source_pdf[page_index].get_links()
            page_region_ids = {region.id for region in page_model.regions}
            protected_boxes = [
                (
                    region.bbox.x0 - 0.5,
                    region.bbox.y0 - 0.5,
                    region.bbox.x1 + 0.5,
                    region.bbox.y1 + 0.5,
                )
                for region in page_model.regions
                if not region.translatable
            ]
            for region_id in sorted(region_ids & page_region_ids):
                region = region_by_id[region_id]
                boxes, cutouts = _redaction_boxes(
                    (region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1),
                    protected_boxes,
                )
                protected_cutouts += cutouts
                for box in boxes:
                    output_page.add_redact_annot(
                        pymupdf.Rect(*box),
                        fill=(1, 1, 1),
                        cross_out=False,
                    )
                    redaction_rectangles += 1
            if region_ids & page_region_ids:
                output_page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )

            shape = output_page.new_shape()
            for placement in lines_by_page.get(page_model.number, []):
                font = resolver.resolve(placement.bold)
                shape.insert_text(
                    pymupdf.Point(placement.x, placement.baseline_y),
                    placement.text,
                    fontname=font.fontname,
                    fontfile=str(font.path),
                    fontsize=placement.font_size,
                    color=_rgb(placement.color),
                    set_simple=False,
                )
                font_counts["bold" if placement.bold else "regular"] += 1
                rendered_lines += 1
            shape.commit(overlay=True)

            for existing_link in output_page.get_links():
                output_page.delete_link(existing_link)
            for source_link in source_links:
                link = {
                    key: value for key, value in source_link.items() if key not in {"xref", "id"}
                }
                output_page.insert_link(link)
                restored_links += 1

        output_pdf.save(
            output_path,
            garbage=4,
            deflate=True,
            deflate_fonts=True,
            use_objstms=True,
        )
        output_pdf.close()

    return TranslatedRenderStats(
        redacted_regions=len(region_ids),
        redaction_rectangles=redaction_rectangles,
        protected_cutouts=protected_cutouts,
        rendered_lines=rendered_lines,
        restored_links=restored_links,
        fonts=dict(font_counts),
    )

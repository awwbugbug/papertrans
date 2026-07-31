from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from papertrans.domain import Document, Region
from papertrans.render.font_mapper import FontResolver


@dataclass(slots=True)
class RenderStats:
    selected_regions: int = 0
    redrawn_regions: int = 0
    redrawn_spans: int = 0
    normalized_spans: int = 0
    restored_links: int = 0
    skipped_regions: list[dict[str, Any]] = field(default_factory=list)
    fonts: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_regions": self.selected_regions,
            "redrawn_regions": self.redrawn_regions,
            "redrawn_spans": self.redrawn_spans,
            "normalized_spans": self.normalized_spans,
            "restored_links": self.restored_links,
            "skipped_regions": self.skipped_regions,
            "fonts": dict(self.fonts),
            "renderer": "native_span_white_redaction_v1",
        }


def _rgb(color: int) -> tuple[float, float, float]:
    red, green, blue = pymupdf.sRGB_to_rgb(color)
    return red / 255, green / 255, blue / 255


def _native_spans(region: Region) -> list[dict[str, Any]]:
    return [
        span
        for line in region.metadata.get("native_lines", [])
        for span in line.get("spans", [])
        if span.get("text")
    ]


def render_roundtrip(
    source_path: str | Path,
    document: Document,
    output_path: str | Path,
    font_resolver: FontResolver | None = None,
) -> RenderStats:
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolver = font_resolver or FontResolver()
    stats = RenderStats()

    with pymupdf.open(source_path) as source_pdf:
        output_pdf = pymupdf.open()
        output_pdf.insert_pdf(source_pdf, links=True, annots=True, widgets=True)
        if source_pdf.metadata:
            output_pdf.set_metadata(source_pdf.metadata)

        for page_index, page_model in enumerate(document.pages):
            source_links = source_pdf[page_index].get_links()
            output_page = output_pdf[page_index]
            selected: list[tuple[Region, list[dict[str, Any]]]] = []
            for region in page_model.regions:
                if not region.translatable or not region.source_text:
                    continue
                stats.selected_regions += 1
                spans = _native_spans(region)
                if not spans:
                    stats.skipped_regions.append(
                        {"region_id": region.id, "reason": "missing_native_spans"}
                    )
                    continue
                selected.append((region, spans))
                output_page.add_redact_annot(
                    pymupdf.Rect(*region.bbox.to_list()),
                    fill=(1, 1, 1),
                    cross_out=False,
                )

            if selected:
                output_page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )

            shape = output_page.new_shape()
            for _region, spans in selected:
                region_span_count = 0
                for span in spans:
                    origin = span.get("origin", [])
                    if len(origin) != 2:
                        continue
                    original_text = str(span.get("text", ""))
                    text = unicodedata.normalize("NFKC", original_text)
                    if text != original_text:
                        stats.normalized_spans += 1
                    resolved = resolver.resolve(
                        str(span.get("font", "")),
                        int(span.get("flags", 0)),
                    )
                    shape.insert_text(
                        pymupdf.Point(float(origin[0]), float(origin[1])),
                        text,
                        fontname=resolved.fontname,
                        fontfile=resolved.fontfile,
                        fontsize=float(span.get("size", 10.0)),
                        color=_rgb(int(span.get("color", 0))),
                        set_simple=False,
                    )
                    stats.fonts[resolved.key] += 1
                    stats.redrawn_spans += 1
                    region_span_count += 1
                if region_span_count:
                    stats.redrawn_regions += 1
            shape.commit(overlay=True)
            for existing_link in output_page.get_links():
                output_page.delete_link(existing_link)
            for source_link in source_links:
                link = {
                    key: value for key, value in source_link.items() if key not in {"xref", "id"}
                }
                output_page.insert_link(link)
                stats.restored_links += 1

        output_pdf.save(
            output_path,
            garbage=4,
            deflate=True,
            deflate_fonts=True,
            use_objstms=True,
        )
        output_pdf.close()
    return stats

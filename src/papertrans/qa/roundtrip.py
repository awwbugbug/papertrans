from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pymupdf


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _pixel_metrics(source_page: pymupdf.Page, output_page: pymupdf.Page) -> dict[str, float]:
    source_pixmap = source_page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
    output_pixmap = output_page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
    source_samples = source_pixmap.samples
    output_samples = output_pixmap.samples
    if len(source_samples) != len(output_samples):
        return {"mean_absolute_error": 1.0, "changed_fraction": 1.0}
    total_difference = 0
    changed = 0
    for source_value, output_value in zip(source_samples, output_samples, strict=True):
        difference = abs(source_value - output_value)
        total_difference += difference
        changed += difference > 8
    sample_count = max(1, len(source_samples))
    return {
        "mean_absolute_error": round(total_difference / (255 * sample_count), 6),
        "changed_fraction": round(changed / sample_count, 6),
    }


def evaluate_roundtrip(source_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()
    pages: list[dict[str, Any]] = []
    with pymupdf.open(source_path) as source_pdf, pymupdf.open(output_path) as output_pdf:
        for page_index in range(min(source_pdf.page_count, output_pdf.page_count)):
            source_page = source_pdf[page_index]
            output_page = output_pdf[page_index]
            source_text = _normalize_text(source_page.get_text("text", sort=True))
            output_text = _normalize_text(output_page.get_text("text", sort=True))
            pages.append(
                {
                    "page": page_index + 1,
                    "same_dimensions": source_page.rect == output_page.rect,
                    "text_similarity": round(
                        SequenceMatcher(None, source_text, output_text, autojunk=False).ratio(),
                        6,
                    ),
                    **_pixel_metrics(source_page, output_page),
                }
            )

        source_links = sum(len(page.get_links()) for page in source_pdf)
        output_links = sum(len(page.get_links()) for page in output_pdf)
        return {
            "source_page_count": source_pdf.page_count,
            "output_page_count": output_pdf.page_count,
            "same_page_count": source_pdf.page_count == output_pdf.page_count,
            "same_page_dimensions": all(page["same_dimensions"] for page in pages),
            "source_link_count": source_links,
            "output_link_count": output_links,
            "links_preserved": source_links == output_links,
            "mean_text_similarity": round(
                sum(page["text_similarity"] for page in pages) / max(1, len(pages)),
                6,
            ),
            "mean_visual_error": round(
                sum(page["mean_absolute_error"] for page in pages) / max(1, len(pages)),
                6,
            ),
            "mean_changed_fraction": round(
                sum(page["changed_fraction"] for page in pages) / max(1, len(pages)),
                6,
            ),
            "pages": pages,
        }

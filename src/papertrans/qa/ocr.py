from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from papertrans.domain import Document, Page


@dataclass(frozen=True, slots=True)
class OCRQualityPolicy:
    max_character_error_rate: float = 0.12
    min_token_order_similarity: float = 0.85
    min_character_coverage_ratio: float = 0.80
    max_character_coverage_ratio: float = 1.20

    def to_dict(self) -> dict[str, float]:
        return {
            "max_character_error_rate": self.max_character_error_rate,
            "min_token_order_similarity": self.min_token_order_similarity,
            "min_character_coverage_ratio": self.min_character_coverage_ratio,
            "max_character_coverage_ratio": self.max_character_coverage_ratio,
        }


def _normalized_page_text(page: Page) -> str:
    regions = sorted(
        (region for region in page.regions if region.source_text),
        key=lambda region: (
            region.reading_order is None,
            region.reading_order or 0,
            region.bbox.y0,
            region.bbox.x0,
        ),
    )
    text = " ".join(region.source_text or "" for region in regions)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _edit_distance(reference: str, hypothesis: str) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, reference_character in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_character in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1]
                    + (reference_character != hypothesis_character),
                )
            )
        previous = current
    return previous[-1]


def evaluate_ocr_documents(
    reference: Document,
    recognized: Document,
    *,
    policy: OCRQualityPolicy | None = None,
) -> dict[str, Any]:
    resolved_policy = policy or OCRQualityPolicy()
    page_count = min(len(reference.pages), len(recognized.pages))
    pages: list[dict[str, Any]] = []
    total_reference_count = 0
    total_recognized_count = 0
    total_edit_distance = 0
    weighted_token_similarity = 0.0
    total_reference_tokens = 0
    for page_index in range(page_count):
        reference_page = reference.pages[page_index]
        recognized_page = recognized.pages[page_index]
        reference_value = _normalized_page_text(reference_page)
        recognized_value = _normalized_page_text(recognized_page)
        reference_count = len(reference_value)
        recognized_count = len(recognized_value)
        edit_distance = _edit_distance(reference_value, recognized_value)
        reference_tokens = reference_value.split()
        recognized_tokens = recognized_value.split()
        token_similarity = SequenceMatcher(
            None,
            reference_tokens,
            recognized_tokens,
            autojunk=False,
        ).ratio()
        token_weight = max(1, len(reference_tokens))
        total_reference_count += reference_count
        total_recognized_count += recognized_count
        total_edit_distance += edit_distance
        weighted_token_similarity += token_similarity * token_weight
        total_reference_tokens += token_weight
        pages.append(
            {
                "page_number": page_index + 1,
                "same_dimensions": (
                    abs(reference_page.width - recognized_page.width) <= 0.01
                    and abs(reference_page.height - recognized_page.height) <= 0.01
                ),
                "reference_character_count": reference_count,
                "recognized_character_count": recognized_count,
                "character_error_rate": round(
                    edit_distance / max(1, reference_count),
                    6,
                ),
                "token_order_similarity": round(token_similarity, 6),
                "character_coverage_ratio": round(
                    recognized_count / max(1, reference_count), 6
                ),
            }
        )

    summary = {
        "reference_character_count": total_reference_count,
        "recognized_character_count": total_recognized_count,
        "character_error_rate": round(
            total_edit_distance / max(1, total_reference_count),
            6,
        ),
        "token_order_similarity": round(
            weighted_token_similarity / max(1, total_reference_tokens),
            6,
        ),
        "character_coverage_ratio": round(
            total_recognized_count / max(1, total_reference_count), 6
        ),
    }
    violations: list[str] = []
    if len(reference.pages) != len(recognized.pages):
        violations.append("page_count")
    if not all(page["same_dimensions"] for page in pages):
        violations.append("page_dimensions")
    if summary["character_error_rate"] > resolved_policy.max_character_error_rate:
        violations.append("character_error_rate")
    if summary["token_order_similarity"] < resolved_policy.min_token_order_similarity:
        violations.append("token_order_similarity")
    if not (
        resolved_policy.min_character_coverage_ratio
        <= summary["character_coverage_ratio"]
        <= resolved_policy.max_character_coverage_ratio
    ):
        violations.append("character_coverage")
    return {
        "schema_version": "m6_ocr_quality_v1",
        "passed": not violations,
        "violations": violations,
        "policy": resolved_policy.to_dict(),
        "page_count": page_count,
        "summary": summary,
        "pages": pages,
    }

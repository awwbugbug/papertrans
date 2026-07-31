from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from papertrans.domain import BoundingBox, Document, Page

OCR_PLAN_SCHEMA_VERSION = "m6_ocr_plan_v2"


class OCRAction(StrEnum):
    KEEP_NATIVE = "keep_native"
    RUN_OCR = "run_ocr"
    USE_OCR = "use_ocr"
    REVIEW = "review"
    SKIP_BLANK = "skip_blank"


@dataclass(frozen=True, slots=True)
class OCRPolicy:
    reliable_native_character_count: int = 80
    sparse_overlay_character_count: int = 12
    minimum_native_text_quality_ratio: float = 0.85
    scan_raster_coverage_ratio: float = 0.60
    minimum_ocr_character_count: int = 40
    minimum_ocr_confidence: float = 0.80

    def to_dict(self) -> dict[str, int | float]:
        return {
            "reliable_native_character_count": self.reliable_native_character_count,
            "sparse_overlay_character_count": self.sparse_overlay_character_count,
            "minimum_native_text_quality_ratio": self.minimum_native_text_quality_ratio,
            "scan_raster_coverage_ratio": self.scan_raster_coverage_ratio,
            "minimum_ocr_character_count": self.minimum_ocr_character_count,
            "minimum_ocr_confidence": self.minimum_ocr_confidence,
        }


@dataclass(frozen=True, slots=True)
class OCRPageDiagnostics:
    native_character_count: int
    native_text_region_count: int
    native_text_quality_ratio: float
    raster_image_coverage_ratio: float
    native_drawing_count: int
    ocr_character_count: int
    ocr_text_region_count: int
    ocr_mean_confidence: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "native_character_count": self.native_character_count,
            "native_text_region_count": self.native_text_region_count,
            "native_text_quality_ratio": round(self.native_text_quality_ratio, 4),
            "raster_image_coverage_ratio": round(self.raster_image_coverage_ratio, 4),
            "native_drawing_count": self.native_drawing_count,
            "ocr_character_count": self.ocr_character_count,
            "ocr_text_region_count": self.ocr_text_region_count,
            "ocr_mean_confidence": round(self.ocr_mean_confidence, 4),
        }


@dataclass(frozen=True, slots=True)
class OCRPageDecision:
    page_number: int
    action: OCRAction
    confidence: float
    reason_codes: tuple[str, ...]
    diagnostics: OCRPageDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "action": self.action.value,
            "confidence": round(self.confidence, 4),
            "reason_codes": list(self.reason_codes),
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class OCRPlan:
    policy: OCRPolicy
    pages: tuple[OCRPageDecision, ...]
    ocr_backend: str | None = None

    @property
    def blocking_page_numbers(self) -> tuple[int, ...]:
        return tuple(
            page.page_number
            for page in self.pages
            if page.action in {OCRAction.RUN_OCR, OCRAction.REVIEW}
        )

    @property
    def summary(self) -> dict[str, int]:
        return {
            "page_count": len(self.pages),
            "keep_native_count": sum(
                page.action is OCRAction.KEEP_NATIVE for page in self.pages
            ),
            "run_ocr_count": sum(page.action is OCRAction.RUN_OCR for page in self.pages),
            "use_ocr_count": sum(page.action is OCRAction.USE_OCR for page in self.pages),
            "review_count": sum(page.action is OCRAction.REVIEW for page in self.pages),
            "skip_blank_count": sum(
                page.action is OCRAction.SKIP_BLANK for page in self.pages
            ),
            "blocking_page_count": len(self.blocking_page_numbers),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OCR_PLAN_SCHEMA_VERSION,
            "mode": "native_first_page_selection",
            "ocr_backend": self.ocr_backend,
            "policy": self.policy.to_dict(),
            "summary": self.summary,
            "pages": [page.to_dict() for page in self.pages],
        }


class OCRPreflightError(RuntimeError):
    def __init__(self, page_numbers: tuple[int, ...], plan_path: str | Path) -> None:
        self.page_numbers = page_numbers
        self.plan_path = Path(plan_path)
        super().__init__("OCR preflight blocked translation; inspect ocr-plan.json")


def build_ocr_plan(
    document: Document,
    policy: OCRPolicy | None = None,
    *,
    ocr_backend: str | None = None,
) -> OCRPlan:
    resolved_policy = policy or OCRPolicy()
    return OCRPlan(
        policy=resolved_policy,
        pages=tuple(_decide_page(page, resolved_policy) for page in document.pages),
        ocr_backend=ocr_backend,
    )


def annotate_document_with_ocr_plan(document: Document, plan: OCRPlan) -> None:
    decisions = {decision.page_number: decision for decision in plan.pages}
    for page in document.pages:
        page.metadata["ocr"] = decisions[page.number].to_dict()
    document.metadata["ocr_preflight"] = {
        "schema_version": OCR_PLAN_SCHEMA_VERSION,
        "summary": plan.summary,
    }


def _decide_page(page: Page, policy: OCRPolicy) -> OCRPageDecision:
    diagnostics = _diagnose_page(page)
    quality_is_reliable = (
        diagnostics.native_text_quality_ratio >= policy.minimum_native_text_quality_ratio
    )
    scan_like = diagnostics.raster_image_coverage_ratio >= policy.scan_raster_coverage_ratio

    if (
        diagnostics.ocr_character_count >= policy.minimum_ocr_character_count
        and diagnostics.ocr_mean_confidence >= policy.minimum_ocr_confidence
    ):
        action = OCRAction.USE_OCR
        reason = "confident_local_ocr"
        confidence = diagnostics.ocr_mean_confidence
    elif diagnostics.ocr_character_count:
        action = OCRAction.REVIEW
        reason = "insufficient_local_ocr"
        confidence = diagnostics.ocr_mean_confidence
    elif diagnostics.native_character_count and not quality_is_reliable:
        action = OCRAction.RUN_OCR if scan_like else OCRAction.REVIEW
        reason = "unreliable_native_text"
        confidence = 0.9 if scan_like else 0.7
    elif diagnostics.native_character_count >= policy.reliable_native_character_count:
        action = OCRAction.KEEP_NATIVE
        reason = "reliable_native_text"
        confidence = 0.98
    elif scan_like:
        if diagnostics.native_character_count <= policy.sparse_overlay_character_count:
            action = OCRAction.RUN_OCR
            reason = "scan_like_page_without_native_text"
            confidence = 0.95
        else:
            action = OCRAction.REVIEW
            reason = "sparse_text_over_large_raster"
            confidence = 0.75
    elif diagnostics.native_character_count:
        action = OCRAction.KEEP_NATIVE
        reason = "sparse_native_text_without_scan_evidence"
        confidence = 0.8
    elif diagnostics.native_drawing_count:
        action = OCRAction.REVIEW
        reason = "vector_content_without_native_text"
        confidence = 0.7
    elif diagnostics.raster_image_coverage_ratio > 0:
        action = OCRAction.REVIEW
        reason = "raster_content_without_page_scan_evidence"
        confidence = 0.65
    else:
        action = OCRAction.SKIP_BLANK
        reason = "empty_page"
        confidence = 0.98

    return OCRPageDecision(
        page_number=page.number,
        action=action,
        confidence=confidence,
        reason_codes=(reason,),
        diagnostics=diagnostics,
    )


def _diagnose_page(page: Page) -> OCRPageDiagnostics:
    text_regions = [
        region
        for region in page.regions
        if region.source_text and region.metadata.get("content_source") == "native_pdf"
    ]
    ocr_regions = [
        region
        for region in page.regions
        if region.source_text and region.metadata.get("content_source") == "paddleocr"
    ]
    characters = [
        character
        for region in text_regions
        for character in region.source_text or ""
        if not character.isspace()
    ]
    acceptable = sum(_is_acceptable_native_character(character) for character in characters)
    text_quality = acceptable / len(characters) if characters else 1.0
    ocr_characters = [
        character
        for region in ocr_regions
        for character in region.source_text or ""
        if not character.isspace()
    ]
    ocr_mean_confidence = (
        sum(region.confidence for region in ocr_regions) / len(ocr_regions)
        if ocr_regions
        else 0.0
    )
    raster_boxes = [
        region.bbox
        for region in page.regions
        if region.metadata.get("native_block_type") == "image"
    ]
    drawing_count = page.metadata.get("native_drawing_count", 0)
    if not isinstance(drawing_count, int) or isinstance(drawing_count, bool):
        drawing_count = 0
    return OCRPageDiagnostics(
        native_character_count=len(characters),
        native_text_region_count=len(text_regions),
        native_text_quality_ratio=text_quality,
        raster_image_coverage_ratio=_box_union_coverage(page, raster_boxes),
        native_drawing_count=max(0, drawing_count),
        ocr_character_count=len(ocr_characters),
        ocr_text_region_count=len(ocr_regions),
        ocr_mean_confidence=ocr_mean_confidence,
    )


def _is_acceptable_native_character(character: str) -> bool:
    return character != "\ufffd" and unicodedata.category(character) not in {"Cc", "Cs", "Co"}


def _box_union_coverage(page: Page, boxes: list[BoundingBox]) -> float:
    if page.width <= 0 or page.height <= 0 or not boxes:
        return 0.0
    clipped = [
        (
            max(0.0, min(page.width, box.x0)),
            max(0.0, min(page.height, box.y0)),
            max(0.0, min(page.width, box.x1)),
            max(0.0, min(page.height, box.y1)),
        )
        for box in boxes
    ]
    clipped = [box for box in clipped if box[2] > box[0] and box[3] > box[1]]
    x_values = sorted({coordinate for box in clipped for coordinate in (box[0], box[2])})
    area = 0.0
    for x0, x1 in zip(x_values, x_values[1:], strict=False):
        intervals = sorted(
            (box[1], box[3]) for box in clipped if box[0] < x1 and box[2] > x0
        )
        covered_height = 0.0
        if intervals:
            start, end = intervals[0]
            for interval_start, interval_end in intervals[1:]:
                if interval_start <= end:
                    end = max(end, interval_end)
                else:
                    covered_height += end - start
                    start, end = interval_start, interval_end
            covered_height += end - start
        area += (x1 - x0) * covered_height
    return min(1.0, area / (page.width * page.height))

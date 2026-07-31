from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from papertrans.domain import Document, Region
from papertrans.layout.models import DocumentLayout, LinePlacement

Box = tuple[float, float, float, float]

LINE_TOP_FACTOR = 0.95
LINE_BOTTOM_FACTOR = 0.15
COLLISION_CLEARANCE = 0.25


@dataclass(frozen=True, slots=True)
class LayoutSafetyReport:
    missing_flow_count: int = 0
    duplicate_flow_count: int = 0
    unexpected_flow_count: int = 0
    overflow_flow_count: int = 0
    font_floor_flow_count: int = 0
    region_binding_count: int = 0
    page_bounds_count: int = 0
    translated_overlap_count: int = 0
    protected_overlap_count: int = 0

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(
            reason
            for reason, count in (
                ("missing_flow", self.missing_flow_count),
                ("duplicate_flow", self.duplicate_flow_count),
                ("unexpected_flow", self.unexpected_flow_count),
                ("overflow", self.overflow_flow_count),
                ("font_floor", self.font_floor_flow_count),
                ("region_binding", self.region_binding_count),
                ("page_bounds", self.page_bounds_count),
                ("translated_overlap", self.translated_overlap_count),
                ("protected_overlap", self.protected_overlap_count),
            )
            if count > 0
        )

    @property
    def passed(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "passed": self.passed,
            "violations": list(self.violations),
            "counts": {
                "missing_flow": self.missing_flow_count,
                "duplicate_flow": self.duplicate_flow_count,
                "unexpected_flow": self.unexpected_flow_count,
                "overflow": self.overflow_flow_count,
                "font_floor": self.font_floor_flow_count,
                "region_binding": self.region_binding_count,
                "page_bounds": self.page_bounds_count,
                "translated_overlap": self.translated_overlap_count,
                "protected_overlap": self.protected_overlap_count,
            },
        }


def line_slot_box(region: Region, baseline: float, font_size: float) -> Box:
    return (
        region.bbox.x0,
        baseline - font_size * LINE_TOP_FACTOR,
        region.bbox.x1,
        baseline + font_size * LINE_BOTTOM_FACTOR,
    )


def placement_box(placement: LinePlacement, region_by_id: dict[str, Region]) -> Box:
    region = region_by_id[placement.region_id]
    return line_slot_box(region, placement.baseline_y, placement.font_size)


def boxes_overlap(left: Box, right: Box, clearance: float = 0.0) -> bool:
    return min(left[2], right[2] + clearance) > max(left[0], right[0] - clearance) and min(
        left[3], right[3] + clearance
    ) > max(left[1], right[1] - clearance)


def protected_boxes_by_page(document: Document) -> dict[int, list[Box]]:
    return {
        page.number: [
            (region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1)
            for region in page.regions
            if not region.translatable and not region.metadata.get("ocr_background")
        ]
        for page in document.pages
    }


def validate_layout(
    document: Document,
    layout: DocumentLayout,
    *,
    expected_flow_ids: Collection[str] | None = None,
) -> LayoutSafetyReport:
    expected = set(expected_flow_ids) if expected_flow_ids is not None else {
        flow.id for flow in document.text_flows if flow.translatable
    }
    flow_by_id = {flow.id: flow for flow in document.text_flows}
    region_by_id = {region.id: region for page in document.pages for region in page.regions}
    page_by_region = {region.id: page.number for page in document.pages for region in page.regions}
    page_bounds = {page.number: (0.0, 0.0, page.width, page.height) for page in document.pages}
    protected = protected_boxes_by_page(document)

    actual_ids = [flow.flow_id for flow in layout.flows]
    actual = set(actual_ids)
    region_binding_count = 0
    page_bounds_count = 0
    protected_overlap_count = 0
    placement_records: list[tuple[LinePlacement, Box]] = []

    for flow_layout in layout.flows:
        source_flow = flow_by_id.get(flow_layout.flow_id)
        if source_flow is None or tuple(flow_layout.region_ids) != tuple(source_flow.region_ids):
            region_binding_count += 1
        for placement in flow_layout.placements:
            region = region_by_id.get(placement.region_id)
            if (
                region is None
                or placement.flow_id != flow_layout.flow_id
                or placement.region_id not in flow_layout.region_ids
            ):
                region_binding_count += 1
                continue
            expected_page = page_by_region[placement.region_id]
            if placement.page_number != expected_page:
                region_binding_count += 1
                continue
            box = placement_box(placement, region_by_id)
            placement_records.append((placement, box))
            if not _box_inside(box, page_bounds[expected_page]):
                page_bounds_count += 1
            if any(
                boxes_overlap(box, protected_box, COLLISION_CLEARANCE)
                for protected_box in protected[expected_page]
            ):
                protected_overlap_count += 1

    translated_overlap_count = 0
    for index, (left, left_box) in enumerate(placement_records):
        for right, right_box in placement_records[index + 1 :]:
            if left.page_number != right.page_number:
                continue
            if left.flow_id == right.flow_id and left.region_id == right.region_id:
                continue
            if boxes_overlap(left_box, right_box, COLLISION_CLEARANCE):
                translated_overlap_count += 1

    return LayoutSafetyReport(
        missing_flow_count=len(expected - actual),
        duplicate_flow_count=len(actual_ids) - len(actual),
        unexpected_flow_count=len(actual - expected),
        overflow_flow_count=sum(not flow.fit or bool(flow.overflow_text) for flow in layout.flows),
        font_floor_flow_count=sum(
            (
                flow.font_size < 6.0 and flow.font_size < flow.original_font_size
            )
            or flow.font_size / max(0.001, flow.original_font_size) < 0.72
            for flow in layout.flows
        ),
        region_binding_count=region_binding_count,
        page_bounds_count=page_bounds_count,
        translated_overlap_count=translated_overlap_count,
        protected_overlap_count=protected_overlap_count,
    )


def _box_inside(inner: Box, outer: Box) -> bool:
    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )

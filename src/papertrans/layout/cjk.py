from __future__ import annotations

import math
from statistics import median

from papertrans.domain import Document, Region, RegionType, TextFlow
from papertrans.layout.cjk_font import CJKFontResolver, ResolvedCJKFont
from papertrans.layout.constraints import (
    COLLISION_CLEARANCE as _COLLISION_CLEARANCE,
)
from papertrans.layout.constraints import (
    Box,
    protected_boxes_by_page,
)
from papertrans.layout.constraints import (
    boxes_overlap as _boxes_overlap,
)
from papertrans.layout.constraints import (
    line_slot_box as _line_slot_box,
)
from papertrans.layout.constraints import (
    placement_box as _placement_box,
)
from papertrans.layout.models import DocumentLayout, FlowLayout, LinePlacement
from papertrans.translation import TranslationResult

_CANNOT_START = set("，。！？；：、）》】」』％）］｝…")
_CANNOT_END = set("（《【「『（［｛")


def _flow_font_size(flow: TextFlow, regions: list[Region]) -> float:
    sizes = [
        region.style.font_size for region in regions if region.style and region.style.font_size
    ]
    return float(median(sizes)) if sizes else 10.0


def _flow_bold(flow: TextFlow, regions: list[Region]) -> bool:
    if flow.type in {RegionType.TITLE, RegionType.HEADING}:
        return True
    flags = [region.style.flags for region in regions if region.style]
    return bool(flags) and sum(bool(flag & 16) for flag in flags) >= len(flags) / 2


def _take_line(text: str, width: float, font: ResolvedCJKFont, font_size: float) -> tuple[str, str]:
    text = text.lstrip()
    if not text:
        return "", ""
    current = ""
    index = 0
    for index, character in enumerate(text):
        if character == "\n":
            return current.rstrip(), text[index + 1 :]
        candidate = f"{current}{character}"
        if current and font.metrics.text_length(candidate, fontsize=font_size) > width:
            if character in _CANNOT_START and len(current) > 1:
                moved = current[-1]
                return current[:-1].rstrip(), f"{moved}{text[index:]}"
            if current[-1] in _CANNOT_END:
                moved = current[-1]
                return current[:-1].rstrip(), f"{moved}{text[index:]}"
            return current.rstrip(), text[index:]
        current = candidate
    return current.rstrip(), text[index + 1 :]


def _initial_occupancy(document: Document) -> dict[int, list[Box]]:
    return protected_boxes_by_page(document)


def _layout_attempt(
    flow: TextFlow,
    regions: list[Region],
    page_by_region: dict[str, int],
    text: str,
    font_size: float,
    font: ResolvedCJKFont,
    occupied_by_page: dict[int, list[Box]],
) -> tuple[list[LinePlacement], str, int]:
    remaining = text
    placements: list[LinePlacement] = []
    local_occupancy = {
        page_number: list(boxes) for page_number, boxes in occupied_by_page.items()
    }
    blocked_line_slots = 0
    line_height = font_size * 1.15
    for region in regions:
        if not remaining:
            break
        page_number = page_by_region[region.id]
        region_placements: list[LinePlacement] = []
        max_lines = max(1, math.floor((region.bbox.height + font_size * 0.18) / line_height))
        for line_index in range(max_lines):
            if not remaining:
                break
            baseline = region.bbox.y0 + font_size * min(font.metrics.ascender, 1.06)
            baseline += line_index * line_height
            slot_box = _line_slot_box(region, baseline, font_size)
            if any(
                _boxes_overlap(slot_box, blocker, _COLLISION_CLEARANCE)
                for blocker in local_occupancy.get(page_number, [])
            ):
                blocked_line_slots += 1
                continue
            line, remaining = _take_line(remaining, region.bbox.width, font, font_size)
            if not line:
                break
            line_width = font.metrics.text_length(line, fontsize=font_size)
            if flow.type == RegionType.TITLE:
                x = region.bbox.x0 + max(0.0, (region.bbox.width - line_width) / 2)
            else:
                x = region.bbox.x0
            placement = LinePlacement(
                flow_id=flow.id,
                region_id=region.id,
                page_number=page_number,
                text=line,
                x=x,
                baseline_y=baseline,
                font_size=font_size,
                bold=font.bold,
                color=region.style.color if region.style and region.style.color is not None else 0,
            )
            placements.append(placement)
            region_placements.append(placement)
        local_occupancy.setdefault(page_number, []).extend(
            _line_slot_box(region, placement.baseline_y, placement.font_size)
            for placement in region_placements
        )
    return placements, remaining, blocked_line_slots


def _size_steps(original_size: float) -> list[float]:
    minimum = max(6.0, original_size * 0.72)
    steps: list[float] = []
    size = original_size - 0.5
    while size >= minimum:
        steps.append(round(size, 2))
        size -= 0.5
    if not steps or steps[-1] > minimum:
        steps.append(math.ceil(minimum * 100) / 100)
    return steps


def _count_layout_collisions(
    layouts: list[FlowLayout],
    document: Document,
    region_by_id: dict[str, Region],
) -> tuple[int, int]:
    placements = [placement for flow in layouts for placement in flow.placements]
    translated_overlaps = 0
    for index, left in enumerate(placements):
        left_box = _placement_box(left, region_by_id)
        for right in placements[index + 1 :]:
            if left.page_number != right.page_number:
                continue
            if left.flow_id == right.flow_id and left.region_id == right.region_id:
                continue
            right_box = _placement_box(right, region_by_id)
            if _boxes_overlap(left_box, right_box, _COLLISION_CLEARANCE):
                translated_overlaps += 1

    protected_by_page = _initial_occupancy(document)
    protected_overlaps = sum(
        any(
            _boxes_overlap(
                _placement_box(placement, region_by_id),
                protected,
                _COLLISION_CLEARANCE,
            )
            for protected in protected_by_page.get(placement.page_number, [])
        )
        for placement in placements
    )
    return translated_overlaps, protected_overlaps


def build_cjk_layout(
    document: Document,
    translations: dict[str, TranslationResult],
    font_resolver: CJKFontResolver | None = None,
) -> DocumentLayout:
    resolver = font_resolver or CJKFontResolver()
    region_by_id = {region.id: region for page in document.pages for region in page.regions}
    page_by_region = {region.id: page.number for page in document.pages for region in page.regions}
    layouts: list[FlowLayout] = []
    occupied_by_page = _initial_occupancy(document)

    for flow in document.text_flows:
        translation = translations.get(flow.id)
        if not flow.translatable or translation is None:
            continue
        regions = [region_by_id[region_id] for region_id in flow.region_ids]
        original_size = _flow_font_size(flow, regions)
        bold = _flow_bold(flow, regions)
        font = resolver.resolve(bold=bold)
        attempts: list[tuple[str, str, float]] = [
            ("normal", translation.normal, original_size),
        ]
        if translation.compact:
            attempts.append(("compact", translation.compact, original_size))
        for size in _size_steps(original_size):
            attempts.append(("normal", translation.normal, size))
            if translation.compact:
                attempts.append(("compact", translation.compact, size))

        selected: FlowLayout | None = None
        for attempt_index, (variant, text, size) in enumerate(attempts, start=1):
            placements, overflow, blocked_line_slots = _layout_attempt(
                flow,
                regions,
                page_by_region,
                text,
                size,
                font,
                occupied_by_page,
            )
            selected = FlowLayout(
                flow_id=flow.id,
                region_ids=flow.region_ids,
                variant=variant,
                original_font_size=original_size,
                font_size=size,
                fit=not overflow,
                overflow_text=overflow,
                placements=placements,
                attempts=attempt_index,
                blocked_line_slots=blocked_line_slots,
            )
            if not overflow:
                break
        if selected is not None:
            layouts.append(selected)
            for placement in selected.placements:
                occupied_by_page.setdefault(placement.page_number, []).append(
                    _placement_box(placement, region_by_id)
                )

    translated_overlaps, protected_overlaps = _count_layout_collisions(
        layouts,
        document,
        region_by_id,
    )

    stats = {
        "flow_count": len(layouts),
        "fit_flow_count": sum(flow.fit for flow in layouts),
        "overflow_flow_count": sum(not flow.fit for flow in layouts),
        "compact_flow_count": sum(flow.variant == "compact" for flow in layouts),
        "reduced_font_flow_count": sum(
            flow.font_size < flow.original_font_size for flow in layouts
        ),
        "minimum_font_size": round(min((flow.font_size for flow in layouts), default=0.0), 3),
        "minimum_font_scale": round(
            min(
                (flow.font_size / max(0.001, flow.original_font_size) for flow in layouts),
                default=1.0,
            ),
            4,
        ),
        "new_sub_6pt_flow_count": sum(
            flow.font_size < 6.0 and flow.font_size < flow.original_font_size for flow in layouts
        ),
        "line_count": sum(len(flow.placements) for flow in layouts),
        "overflow_characters": sum(len(flow.overflow_text) for flow in layouts),
        "blocked_line_slot_count": sum(flow.blocked_line_slots for flow in layouts),
        "translated_line_overlap_count": translated_overlaps,
        "protected_region_overlap_count": protected_overlaps,
    }
    normal_path = resolver.resolve(False).path
    bold_path = resolver.resolve(True).path
    return DocumentLayout(
        font_path=str(normal_path),
        bold_font_path=str(bold_path),
        flows=layouts,
        stats=stats,
    )

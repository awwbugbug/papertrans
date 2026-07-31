from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LinePlacement:
    flow_id: str
    region_id: str
    page_number: int
    text: str
    x: float
    baseline_y: float
    font_size: float
    bold: bool
    color: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "region_id": self.region_id,
            "page_number": self.page_number,
            "text": self.text,
            "x": round(self.x, 3),
            "baseline_y": round(self.baseline_y, 3),
            "font_size": round(self.font_size, 3),
            "bold": self.bold,
            "color": self.color,
        }


@dataclass(slots=True)
class FlowLayout:
    flow_id: str
    region_ids: list[str]
    variant: str
    original_font_size: float
    font_size: float
    fit: bool
    overflow_text: str
    placements: list[LinePlacement] = field(default_factory=list)
    attempts: int = 1
    blocked_line_slots: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "region_ids": self.region_ids,
            "variant": self.variant,
            "original_font_size": round(self.original_font_size, 3),
            "font_size": round(self.font_size, 3),
            "font_scale": round(self.font_size / max(0.001, self.original_font_size), 4),
            "fit": self.fit,
            "overflow_characters": len(self.overflow_text),
            "overflow_text": self.overflow_text,
            "attempts": self.attempts,
            "blocked_line_slots": self.blocked_line_slots,
            "placements": [placement.to_dict() for placement in self.placements],
        }


@dataclass(slots=True)
class DocumentLayout:
    font_path: str
    bold_font_path: str
    flows: list[FlowLayout]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "font_path": self.font_path,
            "bold_font_path": self.bold_font_path,
            "stats": self.stats,
            "flows": [flow.to_dict() for flow in self.flows],
        }

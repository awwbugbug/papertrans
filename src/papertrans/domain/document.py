from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from papertrans.domain.geometry import BoundingBox
from papertrans.domain.styles import TextStyle


class RegionType(StrEnum):
    TITLE = "title"
    AUTHOR = "author"
    AFFILIATION = "affiliation"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    ABSTRACT = "abstract"
    FIGURE = "figure"
    FIGURE_TEXT = "figure_text"
    FIGURE_CAPTION = "figure_caption"
    TABLE = "table"
    TABLE_TEXT = "table_text"
    TABLE_CAPTION = "table_caption"
    FORMULA = "formula"
    HEADER = "header"
    FOOTER = "footer"
    FOOTNOTE = "footnote"
    REFERENCE = "reference"
    PAGE_NUMBER = "page_number"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Region:
    id: str
    type: RegionType
    bbox: BoundingBox
    source_text: str | None = None
    translation: str | None = None
    style: TextStyle | None = None
    reading_order: int | None = None
    translatable: bool = True
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "bbox": self.bbox.to_list(),
            "source_text": self.source_text,
            "translation": self.translation,
            "style": self.style.to_dict() if self.style else None,
            "reading_order": self.reading_order,
            "translatable": self.translatable,
            "confidence": round(self.confidence, 4),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class TextFlow:
    id: str
    type: RegionType
    region_ids: list[str]
    page_numbers: list[int]
    raw_text: str
    source_text: str
    translatable: bool
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "region_ids": self.region_ids,
            "page_numbers": self.page_numbers,
            "raw_text": self.raw_text,
            "source_text": self.source_text,
            "translatable": self.translatable,
            "confidence": round(self.confidence, 4),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class Page:
    number: int
    width: float
    height: float
    regions: list[Region] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "metadata": self.metadata,
            "regions": [region.to_dict() for region in self.regions],
        }


@dataclass(slots=True)
class Document:
    source_path: str
    pages: list[Page] = field(default_factory=list)
    text_flows: list[TextFlow] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "0.3"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "metadata": self.metadata,
            "pages": [page.to_dict() for page in self.pages],
            "text_flows": [flow.to_dict() for flow in self.text_flows],
        }

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from papertrans.domain import Document, RegionType, TextFlow

CONTEXT_SCHEMA_VERSION = "m5c_v1"
MAX_HEADING_CHARS = 200
MAX_NEIGHBOR_CHARS = 600
MAX_GLOSSARY_ENTRIES = 500
MAX_GLOSSARY_TERM_CHARS = 200
_HEADING_TYPES = frozenset({RegionType.TITLE, RegionType.HEADING})
_INVALID_GLOSSARY = "Invalid glossary file"


@dataclass(frozen=True, slots=True)
class TranslationContextStats:
    flow_count: int
    section_title_count: int
    previous_context_count: int
    next_context_count: int
    glossary_term_count: int
    clipped_heading_count: int
    clipped_neighbor_count: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "flow_count": self.flow_count,
            "section_title_count": self.section_title_count,
            "previous_context_count": self.previous_context_count,
            "next_context_count": self.next_context_count,
            "glossary_term_count": self.glossary_term_count,
            "clipped_heading_count": self.clipped_heading_count,
            "clipped_neighbor_count": self.clipped_neighbor_count,
        }


def load_glossary(path: str | Path) -> dict[str, str]:
    try:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        raise ValueError(_INVALID_GLOSSARY) from None
    return _normalize_glossary(payload)


def _normalize_glossary(payload: object) -> dict[str, str]:
    if not isinstance(payload, Mapping) or len(payload) > MAX_GLOSSARY_ENTRIES:
        raise ValueError(_INVALID_GLOSSARY)

    glossary: dict[str, str] = {}
    normalized_terms: set[str] = set()
    for source, target in payload.items():
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError(_INVALID_GLOSSARY)
        normalized_source = source.strip()
        normalized_target = target.strip()
        folded = normalized_source.casefold()
        if (
            not normalized_source
            or not normalized_target
            or len(normalized_source) > MAX_GLOSSARY_TERM_CHARS
            or len(normalized_target) > MAX_GLOSSARY_TERM_CHARS
            or folded in normalized_terms
        ):
            raise ValueError(_INVALID_GLOSSARY)
        normalized_terms.add(folded)
        glossary[normalized_source] = normalized_target
    return glossary


def build_translation_contexts(
    document: Document,
    glossary: Mapping[str, str] | None = None,
) -> tuple[dict[str, dict[str, Any]], TranslationContextStats]:
    ordered_flows = [
        flow for flow in document.text_flows if flow.translatable and flow.source_text.strip()
    ]
    normalized_glossary = _normalize_glossary(glossary or {})
    glossary_items = sorted(
        normalized_glossary.items(),
        key=lambda item: item[0].casefold(),
    )
    active_heading_by_flow = _active_headings(ordered_flows)
    contexts: dict[str, dict[str, Any]] = {}
    clipped_heading_ids: set[str] = set()
    clipped_neighbor_ids: set[str] = set()

    for index, flow in enumerate(ordered_flows):
        previous = ordered_flows[index - 1] if index > 0 else None
        following = ordered_flows[index + 1] if index + 1 < len(ordered_flows) else None
        heading = active_heading_by_flow.get(flow.id)
        section_title, heading_clipped = _clip_text(
            heading.source_text if heading is not None else "",
            MAX_HEADING_CHARS,
        )
        previous_text, previous_clipped = _clip_text(
            previous.source_text if previous is not None else "",
            MAX_NEIGHBOR_CHARS,
        )
        next_text, next_clipped = _clip_text(
            following.source_text if following is not None else "",
            MAX_NEIGHBOR_CHARS,
        )
        if heading_clipped and heading is not None:
            clipped_heading_ids.add(heading.id)
        if previous_clipped and previous is not None:
            clipped_neighbor_ids.add(previous.id)
        if next_clipped and following is not None:
            clipped_neighbor_ids.add(following.id)

        folded_source = flow.source_text.casefold()
        relevant_terms = [
            {"source": source, "target": target}
            for source, target in glossary_items
            if source.casefold() in folded_source
        ]
        contexts[flow.id] = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "region_type": flow.type.value,
            "section_title": section_title,
            "previous_text": previous_text,
            "next_text": next_text,
            "glossary": relevant_terms,
        }

    return contexts, TranslationContextStats(
        flow_count=len(ordered_flows),
        section_title_count=sum(bool(item["section_title"]) for item in contexts.values()),
        previous_context_count=sum(bool(item["previous_text"]) for item in contexts.values()),
        next_context_count=sum(bool(item["next_text"]) for item in contexts.values()),
        glossary_term_count=len(glossary_items),
        clipped_heading_count=len(clipped_heading_ids),
        clipped_neighbor_count=len(clipped_neighbor_ids),
    )


def _active_headings(flows: list[TextFlow]) -> dict[str, TextFlow]:
    active: TextFlow | None = None
    headings: dict[str, TextFlow] = {}
    for flow in flows:
        if flow.type in _HEADING_TYPES:
            active = flow
        if active is not None:
            headings[flow.id] = active
    return headings


def _clip_text(text: str, limit: int) -> tuple[str, bool]:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized, False
    return f"{normalized[: limit - 3].rstrip()}...", True

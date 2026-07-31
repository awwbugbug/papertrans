from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from papertrans.domain import Document, Page, Region, RegionType, TextFlow

_TERMINAL_PUNCTUATION = re.compile(r"[.!?;:][\])}\"'’”]*$")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z-]{2,}")
_LEFT_HYPHEN_FRAGMENT = re.compile(r"([A-Za-z]+)-$")
_RIGHT_HYPHEN_FRAGMENT = re.compile(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
_BODY_TYPES = {RegionType.PARAGRAPH, RegionType.ABSTRACT}
_FLOW_TYPES = {
    RegionType.TITLE,
    RegionType.AUTHOR,
    RegionType.AFFILIATION,
    RegionType.HEADING,
    RegionType.PARAGRAPH,
    RegionType.ABSTRACT,
    RegionType.FIGURE_CAPTION,
    RegionType.TABLE_CAPTION,
    RegionType.FOOTNOTE,
    RegionType.REFERENCE,
}
_PRESERVED_COMPOUNDS = {
    ("class", "specific"),
    ("end", "to-end"),
    ("fine", "tuning"),
    ("fully", "connected"),
    ("ground", "truth"),
    ("high", "level"),
    ("image", "wise"),
    ("low", "level"),
    ("local", "to-global"),
    ("mini", "batches"),
    ("multi", "layer"),
    ("multi", "stage"),
    ("object", "proposal"),
    ("one", "vs-rest"),
    ("per", "pixel"),
    ("pixel", "wise"),
    ("pixels", "to-pixels"),
    ("parameter", "free"),
    ("real", "time"),
    ("region", "based"),
    ("state", "of-the-art"),
    ("test", "time"),
    ("training", "time"),
    ("fully", "convolutional"),
    ("fine", "tune"),
    ("class", "agnostic"),
    ("down", "sampled"),
    ("layer", "by-layer"),
}


@dataclass(frozen=True, slots=True)
class ContinuityEdge:
    previous_region_id: str
    next_region_id: str
    boundary: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "previous_region_id": self.previous_region_id,
            "next_region_id": self.next_region_id,
            "boundary": self.boundary,
            "confidence": self.confidence,
        }


class _DisjointSet:
    def __init__(self, ids: list[str]) -> None:
        self.parent = {item: item for item in ids}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _document_lexicon(regions: list[Region]) -> set[str]:
    words: set[str] = set()
    for region in regions:
        normalized = unicodedata.normalize("NFKC", region.source_text or "")
        for token in _TOKEN.findall(normalized.replace("\n", " ")):
            if "-" not in token:
                words.add(token.casefold())
    return words


def _dehyphenation_action(left: str, right: str, lexicon: set[str]) -> tuple[str, float]:
    pair = (left.casefold(), right.casefold())
    combined = f"{left}{right}".casefold()
    hyphenated = f"{left}-{right}".casefold()
    if not right[:1].islower():
        return "preserve", 0.95
    if pair in _PRESERVED_COMPOUNDS or hyphenated in lexicon:
        return "preserve", 0.9
    if combined in lexicon:
        return "remove", 0.9
    if len(left) <= 3:
        return "remove", 0.72
    return "remove", 0.58


def normalize_fragments(
    fragments: list[str], lexicon: set[str] | None = None
) -> tuple[str, list[dict[str, object]]]:
    """Normalize PDF physical lines while recording every dehyphenation decision."""

    lexicon = lexicon or set()
    lines: list[str] = []
    for fragment in fragments:
        normalized = unicodedata.normalize("NFKC", fragment)
        lines.extend(line.strip() for line in normalized.splitlines() if line.strip())
    if not lines:
        return "", []

    result = lines[0]
    decisions: list[dict[str, object]] = []
    for line_index, line in enumerate(lines[1:], start=1):
        left_match = _LEFT_HYPHEN_FRAGMENT.search(result.rstrip())
        right_match = _RIGHT_HYPHEN_FRAGMENT.match(line)
        if left_match and right_match:
            left = left_match.group(1)
            right = right_match.group(1)
            action, confidence = _dehyphenation_action(left, right, lexicon)
            if action == "remove":
                result = result.rstrip()[:-1] + line
            else:
                result = result.rstrip() + line
            decisions.append(
                {
                    "line_index": line_index,
                    "left": left,
                    "right": right,
                    "action": action,
                    "confidence": confidence,
                }
            )
        else:
            result = f"{result.rstrip()} {line.lstrip()}"

    return re.sub(r"\s+", " ", result).strip(), decisions


def _starts_with_lowercase(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text).lstrip(" ([{\"'‘“")
    return bool(normalized) and normalized[0].islower()


def _ends_with_terminal(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text).rstrip()
    return bool(_TERMINAL_PUNCTUATION.search(normalized))


def _font_compatible(previous: Region, following: Region) -> bool:
    previous_size = previous.style.font_size if previous.style else None
    following_size = following.style.font_size if following.style else None
    if not previous_size or not following_size:
        return True
    ratio = following_size / previous_size
    return 0.82 <= ratio <= 1.22


def _looks_like_prose(region: Region) -> bool:
    normalized = unicodedata.normalize("NFKC", region.source_text or "")
    letters = sum(character.isalpha() for character in normalized)
    digits = sum(character.isdigit() for character in normalized)
    math_symbols = sum(character in "=∑∫√±×÷≤≥≈≠∞^_{}" for character in normalized)
    words = re.findall(r"[A-Za-z]{3,}", normalized)
    signal = letters + digits + math_symbols
    standard_prose = (
        len(words) >= 4
        and signal > 0
        and letters / signal >= 0.82
        and digits <= max(4, round(letters * 0.12))
    )
    numeric_continuation = (
        len(normalized) <= 100
        and len(words) >= 2
        and signal > 0
        and letters / signal >= 0.65
        and digits <= max(12, round(letters * 0.4))
    )
    return standard_prose or numeric_continuation


def _looks_continuous(previous: Region, following: Region) -> bool:
    return (
        previous.type == following.type
        and previous.type in _BODY_TYPES
        and previous.translatable
        and following.translatable
        and _looks_like_prose(previous)
        and _looks_like_prose(following)
        and not _ends_with_terminal(previous.source_text or "")
        and _starts_with_lowercase(following.source_text or "")
        and _font_compatible(previous, following)
    )


def _semantic_regions(page: Page) -> list[Region]:
    return sorted(
        (
            region
            for region in page.regions
            if region.source_text
            and region.reading_order is not None
            and region.type in _FLOW_TYPES
        ),
        key=lambda region: region.reading_order or 0,
    )


def _continuity_edges(document: Document) -> list[ContinuityEdge]:
    edges: list[ContinuityEdge] = []
    for page in document.pages:
        semantic = _semantic_regions(page)
        for column in (1, 2):
            column_regions = [
                region for region in semantic if region.metadata.get("column_index") == column
            ]
            for previous, following in zip(column_regions, column_regions[1:], strict=False):
                gap = following.bbox.y0 - previous.bbox.y1
                font_size = previous.style.font_size if previous.style else 10.0
                if _looks_continuous(previous, following) and gap <= max(8.0, font_size * 1.8):
                    edges.append(ContinuityEdge(previous.id, following.id, "same_column", 0.88))

        left_body = [
            region
            for region in semantic
            if region.type in _BODY_TYPES and region.metadata.get("column_index") == 1
        ]
        right_body = [
            region
            for region in semantic
            if region.type in _BODY_TYPES and region.metadata.get("column_index") == 2
        ]
        if left_body and right_body:
            previous = left_body[-1]
            following = right_body[0]
            if (
                _looks_continuous(previous, following)
                and previous.bbox.y1 >= page.height * 0.72
                and following.bbox.y0 <= page.height * 0.55
            ):
                edges.append(ContinuityEdge(previous.id, following.id, "cross_column", 0.84))

    for previous_page, following_page in zip(document.pages, document.pages[1:], strict=False):
        previous_body = [
            region for region in _semantic_regions(previous_page) if region.type in _BODY_TYPES
        ]
        following_body = [
            region for region in _semantic_regions(following_page) if region.type in _BODY_TYPES
        ]
        if not previous_body or not following_body:
            continue
        previous = previous_body[-1]
        following = following_body[0]
        if (
            _looks_continuous(previous, following)
            and previous.bbox.y1 >= previous_page.height * 0.72
            and following.bbox.y0 <= following_page.height * 0.3
        ):
            edges.append(ContinuityEdge(previous.id, following.id, "cross_page", 0.8))
    return edges


def build_text_flows(document: Document) -> list[TextFlow]:
    ordered_regions = [region for page in document.pages for region in _semantic_regions(page)]
    by_id = {region.id: region for region in ordered_regions}
    page_by_region = {
        region.id: page.number for page in document.pages for region in _semantic_regions(page)
    }
    region_position = {region.id: index for index, region in enumerate(ordered_regions)}
    disjoint_set = _DisjointSet(list(by_id))
    edges = _continuity_edges(document)
    for edge in edges:
        disjoint_set.union(edge.previous_region_id, edge.next_region_id)

    groups: dict[str, list[Region]] = defaultdict(list)
    for region in ordered_regions:
        groups[disjoint_set.find(region.id)].append(region)
    lexicon = _document_lexicon(ordered_regions)

    flows: list[TextFlow] = []
    ordered_groups = sorted(groups.values(), key=lambda items: region_position[items[0].id])
    for regions in ordered_groups:
        regions.sort(key=lambda region: region_position[region.id])
        region_ids = [region.id for region in regions]
        relevant_edges = [
            edge
            for edge in edges
            if edge.previous_region_id in region_ids and edge.next_region_id in region_ids
        ]
        raw_fragments = [region.source_text or "" for region in regions]
        source_text, dehyphenations = normalize_fragments(raw_fragments, lexicon)
        first = regions[0]
        flow_id = f"flow-{first.id}"
        for region in regions:
            region.metadata["text_flow_id"] = flow_id
        confidence = min((edge.confidence for edge in relevant_edges), default=1.0)
        flows.append(
            TextFlow(
                id=flow_id,
                type=first.type,
                region_ids=region_ids,
                page_numbers=list(
                    dict.fromkeys(page_by_region[region_id] for region_id in region_ids)
                ),
                raw_text="\n".join(raw_fragments),
                source_text=source_text,
                translatable=all(region.translatable for region in regions),
                confidence=confidence,
                metadata={
                    "continuity_edges": [edge.to_dict() for edge in relevant_edges],
                    "dehyphenations": dehyphenations,
                    "content_sources": sorted(
                        {
                            str(region.metadata.get("content_source", "unknown"))
                            for region in regions
                        }
                    ),
                    "content_confidence": min(
                        (
                            float(region.metadata.get("content_confidence", 1.0))
                            for region in regions
                        ),
                        default=1.0,
                    ),
                },
            )
        )

    document.text_flows = flows
    document.metadata["text_flow_stats"] = {
        "flow_count": len(flows),
        "merged_flow_count": sum(len(flow.region_ids) > 1 for flow in flows),
        "cross_column_edges": sum(edge.boundary == "cross_column" for edge in edges),
        "cross_page_edges": sum(edge.boundary == "cross_page" for edge in edges),
        "same_column_edges": sum(edge.boundary == "same_column" for edge in edges),
        "dehyphenation_count": sum(len(flow.metadata.get("dehyphenations", [])) for flow in flows),
    }
    return flows

from __future__ import annotations

import re
import unicodedata
from statistics import median

from papertrans.domain import Document, Page, Region, RegionType
from papertrans.structure.text_flow import build_text_flows

_FIGURE_CAPTION = re.compile(r"^(?:figure|fig\.)\s*\d+[.:]?\s*", re.IGNORECASE)
_TABLE_CAPTION = re.compile(r"^table\s*[ivxlcdm\d]+[.:]?\s*", re.IGNORECASE)
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][^.!?]{0,100}$")
_MATH_SYMBOLS = set("=∑∫√λσφ±×÷≤≥≈≠∞^_{}⌊⌋ˆ˜−∈∥|<>•/")
_PROTECTED_TYPES = {
    RegionType.FIGURE,
    RegionType.FIGURE_TEXT,
    RegionType.TABLE_TEXT,
    RegionType.FORMULA,
    RegionType.HEADER,
    RegionType.FOOTER,
    RegionType.PAGE_NUMBER,
}


def _text(region: Region) -> str:
    return " ".join((region.source_text or "").split())


def _body_font_size(page: Page) -> float:
    sizes = [
        region.style.font_size
        for region in page.regions
        if region.style
        and region.style.font_size
        and region.bbox.width >= page.width * 0.22
        and region.type not in {RegionType.TITLE, RegionType.HEADER, RegionType.FOOTER}
    ]
    return float(median(sizes)) if sizes else 0.0


def _overlap_x(left: Region, right: Region) -> float:
    return max(0.0, min(left.bbox.x1, right.bbox.x1) - max(left.bbox.x0, right.bbox.x0))


def _classify_special_regions(page: Page, body_size: float) -> None:
    for region in page.regions:
        text = _text(region)
        if not text or region.type == RegionType.FIGURE:
            continue

        is_vertical_margin_mark = (
            region.bbox.height > region.bbox.width * 2.2 and region.bbox.x0 < page.width * 0.12
        )
        if is_vertical_margin_mark:
            region.type = RegionType.HEADER
            region.translatable = False
            region.confidence = 0.95
            region.metadata["structure_rule"] = "vertical_margin_mark"
            continue

        if _FIGURE_CAPTION.match(text):
            region.type = RegionType.FIGURE_CAPTION
            region.confidence = 0.95
            region.metadata["structure_rule"] = "figure_caption_prefix"
        elif _TABLE_CAPTION.match(text):
            region.type = RegionType.TABLE_CAPTION
            region.confidence = 0.95
            region.metadata["structure_rule"] = "table_caption_prefix"
        elif (
            region.type == RegionType.PARAGRAPH
            and _NUMBERED_HEADING.match(text)
            and len(text) <= 110
            and (region.style is None or bool(region.style.flags & 16))
        ):
            region.type = RegionType.HEADING
            region.confidence = 0.85
            region.metadata["structure_rule"] = "numbered_bold_heading"

        is_small_bottom_text = (
            body_size > 0
            and region.style is not None
            and region.style.font_size is not None
            and region.style.font_size <= body_size * 0.86
            and region.bbox.y0 >= page.height * 0.82
            and region.bbox.width <= page.width * 0.48
            and region.type == RegionType.PARAGRAPH
        )
        if is_small_bottom_text:
            region.type = RegionType.FOOTNOTE
            region.confidence = 0.8
            region.metadata["structure_rule"] = "small_bottom_text"


def _classify_front_matter(page: Page) -> None:
    titles = [region for region in page.regions if region.type == RegionType.TITLE]
    abstract_headings = [
        region
        for region in page.regions
        if region.type == RegionType.HEADING and _text(region).casefold() == "abstract"
    ]
    if not titles or not abstract_headings:
        return

    title = min(titles, key=lambda region: region.bbox.y0)
    abstract_heading = min(abstract_headings, key=lambda region: region.bbox.y0)
    candidates = [
        region
        for region in page.regions
        if region.source_text
        and title.bbox.y1 <= region.bbox.y0 < abstract_heading.bbox.y0
        and region is not title
        and region.bbox.x1 >= page.width * 0.2
        and region.bbox.x0 <= page.width * 0.8
        and region.bbox.width >= page.width * 0.1
    ]
    for index, region in enumerate(sorted(candidates, key=lambda item: item.bbox.y0)):
        region.type = RegionType.AUTHOR if index == 0 else RegionType.AFFILIATION
        region.translatable = region.type == RegionType.AFFILIATION and not any(
            marker in _text(region).casefold() for marker in ("@", "http://", "https://")
        )
        region.confidence = 0.8
        region.metadata["structure_rule"] = "front_matter_between_title_and_abstract"


def _classify_figure_text(page: Page, body_size: float) -> None:
    captions = [region for region in page.regions if region.type == RegionType.FIGURE_CAPTION]
    for caption in captions:
        visual_top = max(0.0, caption.bbox.y0 - page.height * 0.75)
        for region in page.regions:
            if region is caption or not region.source_text or region.type != RegionType.PARAGRAPH:
                continue
            if _is_text_from_accepted_ocr_background(page, region):
                continue
            if not (visual_top <= region.bbox.y0 and region.bbox.y1 <= caption.bbox.y1 + 2):
                continue
            if _overlap_x(region, caption) <= 0:
                continue
            is_figure_sized = region.bbox.width <= caption.bbox.width * 0.78 or (
                body_size > 0
                and region.style is not None
                and region.style.font_size is not None
                and region.style.font_size < body_size * 0.92
            )
            if is_figure_sized:
                region.type = RegionType.FIGURE_TEXT
                region.translatable = False
                region.confidence = 0.82
                region.metadata["structure_rule"] = "text_inside_figure_above_caption"


def _is_text_from_accepted_ocr_background(page: Page, region: Region) -> bool:
    if region.metadata.get("content_source") != "paddleocr":
        return False
    source_region_id = region.metadata.get("ocr_source_region_id")
    backgrounds = [
        candidate
        for candidate in page.regions
        if candidate.metadata.get("ocr_background") is True
    ]
    if source_region_id is not None:
        return any(candidate.id == source_region_id for candidate in backgrounds)
    return any(
        candidate.bbox.x0 <= region.bbox.x0
        and candidate.bbox.y0 <= region.bbox.y0
        and candidate.bbox.x1 >= region.bbox.x1
        and candidate.bbox.y1 >= region.bbox.y1
        for candidate in backgrounds
    )


def _classify_table_text(page: Page, body_size: float) -> None:
    captions = [region for region in page.regions if region.type == RegionType.TABLE_CAPTION]
    for caption in captions:
        table_bottom = min(page.height, caption.bbox.y1 + page.height * 0.35)
        for region in page.regions:
            if region is caption or not region.source_text or region.type != RegionType.PARAGRAPH:
                continue
            if not (caption.bbox.y1 - 2 <= region.bbox.y0 and region.bbox.y1 <= table_bottom):
                continue
            if _overlap_x(region, caption) <= 0:
                continue
            is_table_sized = region.bbox.width <= caption.bbox.width * 0.9 or (
                body_size > 0
                and region.style is not None
                and region.style.font_size is not None
                and region.style.font_size < body_size * 0.92
            )
            if is_table_sized:
                region.type = RegionType.TABLE_TEXT
                region.translatable = False
                region.confidence = 0.78
                region.metadata["structure_rule"] = "text_inside_table_below_caption"


def _classify_formulas(page: Page) -> None:
    formula_regions: list[Region] = []
    for region in page.regions:
        if region.type not in {RegionType.PARAGRAPH, RegionType.HEADING} or not region.source_text:
            continue
        text = unicodedata.normalize("NFKC", _text(region))
        compact_text = re.sub(r"\s+", "", text)
        word_count = len(re.findall(r"[A-Za-z]{3,}", text))
        math_symbol_count = sum(character in _MATH_SYMBOLS for character in text)
        control_count = sum(ord(character) < 32 and not character.isspace() for character in text)
        has_compact_index = len(compact_text) <= 16 and any(
            character.isdigit() for character in compact_text
        )
        looks_like_formula = len(text) <= 240 and (
            control_count > 0
            or ("=" in text and math_symbol_count >= 2 and word_count <= 12)
            or (math_symbol_count >= 4 and word_count <= 8)
            or (math_symbol_count >= 2 and len(text) <= 80 and word_count <= 3)
            or (math_symbol_count >= 1 and len(text) <= 12 and word_count <= 2)
            or (has_compact_index and word_count <= 1)
            or (
                region.type == RegionType.HEADING
                and len(text) <= 40
                and math_symbol_count >= 2
            )
        )
        if looks_like_formula:
            region.type = RegionType.FORMULA
            region.translatable = False
            region.confidence = 0.78
            region.metadata["structure_rule"] = "math_symbol_density"
            formula_regions.append(region)

    # PDF text extractors often split one display equation into many tiny blocks. Once a strong
    # formula fragment is found, protect adjacent single variables, summation markers, and a short
    # label such as "loss function:" as part of the same equation cluster.
    changed = True
    while changed:
        changed = False
        for region in page.regions:
            if region.type != RegionType.PARAGRAPH or not region.source_text:
                continue
            text = unicodedata.normalize("NFKC", _text(region))
            compact_text = re.sub(r"\s+", "", text)
            word_count = len(re.findall(r"[A-Za-z]{3,}", text))
            has_math_token = any(character in _MATH_SYMBOLS for character in text) or any(
                character.isdigit() for character in text
            )
            is_short_formula_fragment = (
                word_count <= 2
                and (len(compact_text) <= 16 or (len(compact_text) <= 50 and has_math_token))
                and not text.casefold().startswith(("note ", "for ", "if "))
            )
            is_formula_label = len(text) <= 40 and text.endswith(":")
            if not (is_short_formula_fragment or is_formula_label):
                continue
            if not any(
                _regions_are_formula_neighbors(region, anchor) for anchor in formula_regions
            ):
                continue
            region.type = RegionType.FORMULA
            region.translatable = False
            region.confidence = 0.74
            region.metadata["structure_rule"] = "adjacent_formula_fragment"
            formula_regions.append(region)
            changed = True


def _regions_are_formula_neighbors(left: Region, right: Region) -> bool:
    horizontal_gap = max(
        0.0,
        left.bbox.x0 - right.bbox.x1,
        right.bbox.x0 - left.bbox.x1,
    )
    vertical_gap = max(
        0.0,
        left.bbox.y0 - right.bbox.y1,
        right.bbox.y0 - left.bbox.y1,
    )
    return horizontal_gap <= 16 and vertical_gap <= 24


def _detect_two_columns(page: Page) -> bool:
    center = page.width / 2
    substantial = [
        region
        for region in page.regions
        if region.source_text
        and region.type not in _PROTECTED_TYPES
        and page.width * 0.22 <= region.bbox.width <= page.width * 0.48
        and region.bbox.height
        >= (6 if region.metadata.get("content_source") == "paddleocr" else 12)
    ]
    left = [region for region in substantial if (region.bbox.x0 + region.bbox.x1) / 2 < center]
    right = [region for region in substantial if (region.bbox.x0 + region.bbox.x1) / 2 >= center]
    return (len(left) >= 2 and len(right) >= 1) or (len(left) >= 1 and len(right) >= 2)


def _assign_columns(page: Page, two_columns: bool) -> None:
    center = page.width / 2
    for region in page.regions:
        if region.type in _PROTECTED_TYPES:
            region.metadata["column_index"] = None
            region.metadata["flow_role"] = "non_body"
            continue

        crosses_center = region.bbox.x0 < center < region.bbox.x1
        if region.type in {RegionType.TITLE, RegionType.AUTHOR, RegionType.AFFILIATION}:
            column = 0
        elif crosses_center and region.bbox.width >= page.width * 0.36:
            column = 0
        elif not two_columns:
            column = 1
        else:
            column = 1 if (region.bbox.x0 + region.bbox.x1) / 2 < center else 2
        region.metadata["column_index"] = column
        region.metadata["flow_role"] = "page_wide" if column == 0 else f"column_{column}"


def _classify_abstract(page: Page) -> None:
    headings = [
        region
        for region in page.regions
        if region.type == RegionType.HEADING and _text(region).casefold() == "abstract"
    ]
    for heading in headings:
        column = heading.metadata.get("column_index")
        next_heading_y = min(
            (
                region.bbox.y0
                for region in page.regions
                if region.type == RegionType.HEADING
                and region is not heading
                and region.metadata.get("column_index") == column
                and region.bbox.y0 > heading.bbox.y0
            ),
            default=page.height,
        )
        for region in page.regions:
            if (
                region.type == RegionType.PARAGRAPH
                and region.metadata.get("column_index") == column
                and heading.bbox.y1 <= region.bbox.y0 < next_heading_y
            ):
                region.type = RegionType.ABSTRACT
                region.confidence = 0.85
                region.metadata["structure_rule"] = "between_abstract_and_next_heading"


def _assign_reading_order(page: Page, two_columns: bool) -> None:
    semantic = [
        region
        for region in page.regions
        if region.source_text and region.type not in _PROTECTED_TYPES
    ]
    column_regions = [
        region for region in semantic if region.metadata.get("column_index") in {1, 2}
    ]
    column_top = min((region.bbox.y0 for region in column_regions), default=page.height)
    page_wide = [region for region in semantic if region.metadata.get("column_index") == 0]
    preamble = [region for region in page_wide if region.bbox.y0 <= column_top + 12]
    trailing_wide = [region for region in page_wide if region not in preamble]

    ordered: list[Region] = sorted(preamble, key=lambda region: (region.bbox.y0, region.bbox.x0))
    if two_columns:
        for column in (1, 2):
            ordered.extend(
                sorted(
                    (
                        region
                        for region in semantic
                        if region.metadata.get("column_index") == column
                    ),
                    key=lambda region: (region.bbox.y0, region.bbox.x0),
                )
            )
    else:
        ordered.extend(
            sorted(
                (region for region in semantic if region.metadata.get("column_index") == 1),
                key=lambda region: (region.bbox.y0, region.bbox.x0),
            )
        )
    ordered.extend(sorted(trailing_wide, key=lambda region: (region.bbox.y0, region.bbox.x0)))

    for region in page.regions:
        region.reading_order = None
    for order, region in enumerate(ordered, start=1):
        region.reading_order = order

    ordered_ids = {id(region) for region in ordered}
    remainder = sorted(
        (region for region in page.regions if id(region) not in ordered_ids),
        key=lambda region: (region.bbox.y0, region.bbox.x0),
    )
    page.regions = ordered + remainder


def recover_page_structure(page: Page) -> None:
    body_size = _body_font_size(page)
    _classify_special_regions(page, body_size)
    _classify_front_matter(page)
    _classify_figure_text(page, body_size)
    _classify_table_text(page, body_size)
    _classify_formulas(page)
    two_columns = _detect_two_columns(page)
    _assign_columns(page, two_columns)
    _classify_abstract(page)
    _assign_reading_order(page, two_columns)
    page.metadata.update(
        {
            "layout": "two_column" if two_columns else "single_column",
            "body_font_size": round(body_size, 3),
            "structure_stage": "m1_heuristic_v1",
            "structure_confidence": 0.72 if two_columns else 0.6,
        }
    )


def _classify_reference_section(document: Document) -> None:
    in_references = False
    for page in document.pages:
        for region in page.regions:
            text = _text(region).casefold()
            if text in {"references", "reference"} and region.type in {
                RegionType.TITLE,
                RegionType.HEADING,
            }:
                region.type = RegionType.HEADING
                region.confidence = 0.95
                region.metadata["structure_rule"] = "references_heading"
                in_references = True
                continue
            if in_references and region.type in {RegionType.PARAGRAPH, RegionType.FOOTNOTE}:
                region.type = RegionType.REFERENCE
                region.translatable = False
                region.confidence = 0.9
                region.metadata["structure_rule"] = "after_references_heading"


def recover_document_structure(document: Document) -> Document:
    for page in document.pages:
        recover_page_structure(page)
    _classify_reference_section(document)
    build_text_flows(document)
    document.metadata["structure_stage"] = "m1_heuristic_v1"
    return document

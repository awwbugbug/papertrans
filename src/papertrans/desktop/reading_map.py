from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf

READING_MAP_SCHEMA_VERSION = "m7_reading_map_v1"


def build_reading_map(output_dir: str | Path, page_number: int) -> dict[str, Any]:
    if page_number < 1:
        raise ValueError("页码必须大于或等于 1")

    root = Path(output_dir).resolve()
    document = _load_object(root / "document.json")
    layout = _load_object(root / "layout.json")
    translations = _load_object(root / "translations.json")

    pages = document.get("pages")
    if not isinstance(pages, list):
        raise ValueError("document.json 缺少页面数据")
    page = next((item for item in pages if item.get("number") == page_number), None)
    if page is None:
        raise ValueError("页码超出文档范围")

    regions = {
        region["id"]: region
        for page_item in pages
        for region in page_item.get("regions", [])
        if isinstance(region, dict) and isinstance(region.get("id"), str)
    }
    region_pages = {
        region["id"]: page_item.get("number")
        for page_item in pages
        for region in page_item.get("regions", [])
        if isinstance(region, dict) and isinstance(region.get("id"), str)
    }
    layouts = {
        item["flow_id"]: item
        for item in layout.get("flows", [])
        if isinstance(item, dict) and isinstance(item.get("flow_id"), str)
    }
    translated = {
        item["segment_id"]: item
        for item in translations.get("translations", [])
        if isinstance(item, dict) and isinstance(item.get("segment_id"), str)
    }
    normal_font = _load_font(layout.get("font_path"), fallback="china-s")
    bold_font = _load_font(layout.get("bold_font_path"), fallback="china-ss")

    paragraphs: list[dict[str, Any]] = []
    for reading_order, flow in enumerate(document.get("text_flows", [])):
        if not isinstance(flow, dict) or not flow.get("translatable"):
            continue
        flow_id = flow.get("id")
        if not isinstance(flow_id, str):
            continue
        flow_layout = layouts.get(flow_id)
        translation = translated.get(flow_id)
        if flow_layout is None or translation is None:
            continue

        source_boxes = [
            _rounded_box(regions[region_id]["bbox"])
            for region_id in flow.get("region_ids", [])
            if region_pages.get(region_id) == page_number
            and region_id in regions
            and _is_box(regions[region_id].get("bbox"))
        ]
        translation_boxes = [
            _placement_box(item, bold_font if item.get("bold") else normal_font)
            for item in flow_layout.get("placements", [])
            if isinstance(item, dict) and item.get("page_number") == page_number
        ]
        if not source_boxes and not translation_boxes:
            continue
        source_page_numbers = sorted(
            {
                int(region_pages[region_id])
                for region_id in flow.get("region_ids", [])
                if isinstance(region_pages.get(region_id), int)
            }
        )
        translation_page_numbers = sorted(
            {
                int(item["page_number"])
                for item in flow_layout.get("placements", [])
                if isinstance(item, dict) and isinstance(item.get("page_number"), int)
            }
        )

        variant = flow_layout.get("variant")
        translated_text = translation.get(variant) if variant in {"normal", "compact"} else None
        if not isinstance(translated_text, str):
            translated_text = "".join(
                str(item.get("text", ""))
                for item in flow_layout.get("placements", [])
                if isinstance(item, dict)
            )
        paragraphs.append(
            {
                "id": flow_id,
                "type": str(flow.get("type", "paragraph")),
                "readingOrder": reading_order,
                "sourceText": str(flow.get("source_text", "")),
                "translation": translated_text,
                "sourcePageNumbers": source_page_numbers,
                "translationPageNumbers": translation_page_numbers,
                "sourceBoxes": source_boxes,
                "translationBoxes": translation_boxes,
            }
        )

    return {
        "schemaVersion": READING_MAP_SCHEMA_VERSION,
        "page": {
            "number": page_number,
            "width": round(float(page["width"]), 3),
            "height": round(float(page["height"]), 3),
        },
        "paragraphs": paragraphs,
    }


def _load_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path.name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} 的根节点必须是对象")
    return payload


def _load_font(value: object, *, fallback: str) -> pymupdf.Font:
    if isinstance(value, str) and Path(value).is_file():
        try:
            return pymupdf.Font(fontfile=value)
        except RuntimeError:
            pass
    return pymupdf.Font(fallback)


def _placement_box(placement: dict[str, Any], font: pymupdf.Font) -> list[float]:
    text = str(placement.get("text", ""))
    x0 = float(placement["x"])
    baseline = float(placement["baseline_y"])
    font_size = float(placement["font_size"])
    width = font.text_length(text, fontsize=font_size)
    return _rounded_box(
        [
            x0,
            baseline - font.ascender * font_size,
            x0 + width,
            baseline - font.descender * font_size,
        ]
    )


def _is_box(value: object) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(
        isinstance(item, int | float) for item in value
    )


def _rounded_box(value: list[object]) -> list[float]:
    return [round(float(item), 3) for item in value]

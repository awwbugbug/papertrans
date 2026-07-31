from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from papertrans.domain import Document, RegionType
from papertrans.ingest import (
    OCRPlan,
    annotate_document_with_ocr_plan,
    build_ocr_plan,
    extract_document,
)

COLORS: dict[RegionType, tuple[float, float, float]] = {
    RegionType.TITLE: (0.85, 0.15, 0.15),
    RegionType.AUTHOR: (0.75, 0.25, 0.15),
    RegionType.AFFILIATION: (0.70, 0.40, 0.15),
    RegionType.HEADING: (0.95, 0.55, 0.05),
    RegionType.PARAGRAPH: (0.05, 0.45, 0.90),
    RegionType.FIGURE: (0.15, 0.65, 0.25),
    RegionType.FIGURE_TEXT: (0.10, 0.60, 0.55),
    RegionType.TABLE: (0.55, 0.20, 0.75),
    RegionType.TABLE_TEXT: (0.45, 0.25, 0.70),
    RegionType.FORMULA: (0.80, 0.10, 0.55),
    RegionType.HEADER: (0.45, 0.45, 0.45),
    RegionType.FOOTER: (0.45, 0.45, 0.45),
    RegionType.PAGE_NUMBER: (0.45, 0.45, 0.45),
}


@dataclass(frozen=True, slots=True)
class InspectionResult:
    output_dir: Path
    document_json: Path
    text_flows_json: Path
    ocr_plan_json: Path
    report_markdown: Path
    document: Document


def _render_pages(source_path: Path, document: Document, output_dir: Path) -> None:
    page_dir = output_dir / "pages"
    overlay_dir = output_dir / "overlays"
    page_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    scale = 1.5
    matrix = pymupdf.Matrix(scale, scale)

    with pymupdf.open(source_path) as source_pdf:
        for page_index, source_page in enumerate(source_pdf):
            page_number = page_index + 1
            source_page.get_pixmap(matrix=matrix, alpha=False).save(
                page_dir / f"page-{page_number:03d}.png"
            )

            overlay_pdf = pymupdf.open()
            overlay_page = overlay_pdf.new_page(
                width=source_page.rect.width,
                height=source_page.rect.height,
            )
            overlay_page.show_pdf_page(overlay_page.rect, source_pdf, page_index)
            for region in document.pages[page_index].regions:
                rect = pymupdf.Rect(*region.bbox.to_list())
                color = COLORS.get(region.type, (0.15, 0.15, 0.15))
                overlay_page.draw_rect(rect, color=color, width=0.8, overlay=True)
                order = f"#{region.reading_order} " if region.reading_order else ""
                label = f"{order}{region.type.value}"
                label_origin = pymupdf.Point(rect.x0 + 1.5, max(7.0, rect.y0 + 7.0))
                overlay_page.insert_text(
                    label_origin,
                    label,
                    fontsize=5.5,
                    color=color,
                    overlay=True,
                )
            ocr_action = str(
                document.pages[page_index].metadata.get("ocr", {}).get("action", "unknown")
            )
            action_color = {
                "keep_native": (0.05, 0.55, 0.20),
                "run_ocr": (0.85, 0.10, 0.10),
                "review": (0.95, 0.50, 0.05),
                "skip_blank": (0.40, 0.40, 0.40),
            }.get(ocr_action, (0.20, 0.20, 0.20))
            banner = pymupdf.Rect(source_page.rect.width - 92, 5, source_page.rect.width - 5, 19)
            overlay_page.draw_rect(
                banner,
                color=action_color,
                fill=(1, 1, 1),
                width=0.8,
                overlay=True,
            )
            overlay_page.insert_text(
                pymupdf.Point(banner.x0 + 3, banner.y0 + 9),
                f"OCR: {ocr_action}",
                fontsize=6,
                color=action_color,
                overlay=True,
            )
            overlay_page.get_pixmap(matrix=matrix, alpha=False).save(
                overlay_dir / f"page-{page_number:03d}-layout.png"
            )
            overlay_pdf.close()


def _write_report(document: Document, ocr_plan: OCRPlan, output_dir: Path) -> Path:
    report_path = output_dir / "inspect-report.md"
    lines = [
        "# PDF inspection report",
        "",
        f"- Source: `{document.source_path}`",
        f"- Pages: {len(document.pages)}",
        f"- Schema: `{document.schema_version}`",
        "- Status: M6.1 native-first OCR routing; OCR execution is not enabled",
        f"- Text flows: {document.metadata.get('text_flow_stats', {}).get('flow_count', 0)}",
        "- Merged flows: "
        f"{document.metadata.get('text_flow_stats', {}).get('merged_flow_count', 0)}",
        "- Cross-column continuations: "
        f"{document.metadata.get('text_flow_stats', {}).get('cross_column_edges', 0)}",
        "- Cross-page continuations: "
        f"{document.metadata.get('text_flow_stats', {}).get('cross_page_edges', 0)}",
        "- Dehyphenation decisions: "
        f"{document.metadata.get('text_flow_stats', {}).get('dehyphenation_count', 0)}",
        f"- Native pages: {ocr_plan.summary['keep_native_count']}",
        f"- OCR candidate pages: {ocr_plan.summary['run_ocr_count']}",
        f"- OCR review pages: {ocr_plan.summary['review_count']}",
        "",
        "## Page summary",
        "",
        "| Page | Regions | Translatable | OCR action | Preview |",
        "| ---: | ---: | ---: | --- | --- |",
    ]
    decisions = {decision.page_number: decision for decision in ocr_plan.pages}
    for page in document.pages:
        translatable = sum(1 for region in page.regions if region.translatable)
        preview = f"[layout](overlays/page-{page.number:03d}-layout.png)"
        action = decisions[page.number].action.value
        lines.append(
            f"| {page.number} | {len(page.regions)} | {translatable} | {action} | {preview} |"
        )
    lines.extend(
        [
            "",
            "## Known limitations",
            "",
            "- Region labels and column reading order remain heuristic.",
            "- Figure and table captions use prefix rules; formula and reference detection "
            "are pending.",
            "- Cross-column headings and irregular magazine-style layouts are not solved yet.",
            "- OCR candidates are detected, but no OCR engine is executed in M6.1.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def inspect_pdf(source: str | Path, output_dir: str | Path) -> InspectionResult:
    source_path = Path(source).expanduser().resolve()
    resolved_output = Path(output_dir).expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)

    document = extract_document(source_path)
    ocr_plan = build_ocr_plan(document)
    annotate_document_with_ocr_plan(document, ocr_plan)
    document_json = resolved_output / "document.json"
    document_json.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    text_flows_json = resolved_output / "text-flows.json"
    text_flows_json.write_text(
        json.dumps(
            {
                "schema_version": document.schema_version,
                "source_path": document.source_path,
                "stats": document.metadata.get("text_flow_stats", {}),
                "text_flows": [flow.to_dict() for flow in document.text_flows],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    ocr_plan_json = resolved_output / "ocr-plan.json"
    ocr_plan_json.write_text(
        json.dumps(ocr_plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _render_pages(source_path, document, resolved_output)
    report = _write_report(document, ocr_plan, resolved_output)
    return InspectionResult(
        output_dir=resolved_output,
        document_json=document_json,
        text_flows_json=text_flows_json,
        ocr_plan_json=ocr_plan_json,
        report_markdown=report,
        document=document,
    )

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from papertrans.ingest import extract_document
from papertrans.qa import evaluate_roundtrip
from papertrans.render import render_roundtrip


@dataclass(frozen=True, slots=True)
class RoundtripResult:
    output_dir: Path
    output_pdf: Path
    document_json: Path
    report_json: Path
    report: dict[str, Any]


def run_roundtrip(source: str | Path, output_dir: str | Path) -> RoundtripResult:
    source_path = Path(source).expanduser().resolve()
    resolved_output = Path(output_dir).expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    output_pdf = resolved_output / "output.pdf"
    temporary_pdf = resolved_output / f".{uuid4().hex}.roundtrip.tmp.pdf"

    document = extract_document(source_path)
    document_json = resolved_output / "document.json"
    document_json.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        render_stats = render_roundtrip(source_path, document, temporary_pdf)
        temporary_pdf.replace(output_pdf)
    finally:
        if temporary_pdf.exists():
            temporary_pdf.unlink()

    quality = evaluate_roundtrip(source_path, output_pdf)
    gates = {
        "same_page_count": quality["same_page_count"],
        "same_page_dimensions": quality["same_page_dimensions"],
        "links_preserved": quality["links_preserved"],
        "no_skipped_regions": not render_stats.skipped_regions,
        "text_similarity_at_least_0_98": quality["mean_text_similarity"] >= 0.98,
    }
    report = {
        "schema_version": "0.1",
        "source_path": str(source_path),
        "output_path": str(output_pdf),
        "mode": "zero_translation_roundtrip",
        "limitations": [
            "White fill is used when removing translated text regions.",
            "Original embedded fonts are mapped to local Times, Arial, or Courier families.",
            "Protected formulas, figures, tables, references, headers, and page numbers "
            "remain original.",
        ],
        "render": render_stats.to_dict(),
        "quality": quality,
        "gates": gates,
        "passed": all(gates.values()),
    }
    report_json = resolved_output / "roundtrip-report.json"
    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return RoundtripResult(
        output_dir=resolved_output,
        output_pdf=output_pdf,
        document_json=document_json,
        report_json=report_json,
        report=report,
    )

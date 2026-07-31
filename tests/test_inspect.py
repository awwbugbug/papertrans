import json
from pathlib import Path

import pymupdf

from papertrans.inspect import inspect_pdf


def _create_sample_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_text((40, 55), "A Small Research Paper", fontsize=18)
    page.insert_text((40, 90), "1 Introduction", fontsize=13)
    page.insert_textbox(
        pymupdf.Rect(40, 110, 190, 300),
        "This is the first column. It contains enough text to create a paragraph block.",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(230, 110, 380, 300),
        "This is the second column. It is kept separate for visual inspection.",
        fontsize=9,
    )
    page.insert_text((205, 570), "1", fontsize=8)
    document.save(path)
    document.close()


def test_inspect_pdf_writes_document_and_previews(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    output = tmp_path / "inspection"
    _create_sample_pdf(source)

    result = inspect_pdf(source, output)
    payload = json.loads(result.document_json.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "0.3"
    assert len(payload["pages"]) == 1
    assert any(region["type"] == "title" for region in payload["pages"][0]["regions"])
    assert (output / "pages" / "page-001.png").is_file()
    assert (output / "overlays" / "page-001-layout.png").is_file()
    assert result.text_flows_json.is_file()
    assert payload["text_flows"]
    assert result.ocr_plan_json.is_file()
    ocr_plan = json.loads(result.ocr_plan_json.read_text(encoding="utf-8"))
    assert ocr_plan["schema_version"] == "m6_ocr_plan_v1"
    assert ocr_plan["pages"][0]["action"] == "keep_native"
    assert payload["pages"][0]["metadata"]["ocr"]["action"] == "keep_native"
    assert payload["text_flows"][0]["metadata"]["content_sources"] == ["native_pdf"]
    assert result.report_markdown.is_file()
    assert "keep_native" in result.report_markdown.read_text(encoding="utf-8")

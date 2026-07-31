from pathlib import Path

import pymupdf

from papertrans.roundtrip import run_roundtrip


def _create_roundtrip_fixture(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_text((40, 60), "Roundtrip Research Paper", fontsize=18, fontname="tibo")
    page.insert_text((40, 100), "1. Introduction", fontsize=13, fontname="tibo")
    page.insert_textbox(
        pymupdf.Rect(40, 120, 190, 300),
        "This is the left column. It contains a complete scientific paragraph.",
        fontsize=9,
        fontname="tiro",
    )
    page.insert_textbox(
        pymupdf.Rect(230, 120, 380, 300),
        "This is the right column. It remains selectable after reconstruction.",
        fontsize=9,
        fontname="tiro",
    )
    page.insert_text((205, 570), "1", fontsize=8)
    document.save(path)
    document.close()


def test_roundtrip_rebuilds_text_and_preserves_page_geometry(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    output_dir = tmp_path / "roundtrip"
    _create_roundtrip_fixture(source)

    result = run_roundtrip(source, output_dir)

    assert result.output_pdf.is_file()
    assert result.document_json.is_file()
    assert result.report_json.is_file()
    assert result.report["quality"]["same_page_count"] is True
    assert result.report["quality"]["same_page_dimensions"] is True
    assert result.report["quality"]["mean_text_similarity"] >= 0.98
    assert result.report["render"]["redrawn_spans"] > 0

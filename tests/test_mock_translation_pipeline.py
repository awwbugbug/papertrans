from pathlib import Path

import pymupdf

from papertrans.mock_translation import run_mock_translation


def _create_mock_fixture(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_text((80, 60), "Research", fontsize=18, fontname="tibo")
    page.insert_text((40, 100), "1. Introduction", fontsize=13, fontname="tibo")
    page.insert_textbox(
        pymupdf.Rect(40, 120, 190, 360),
        "This scientific paragraph provides enough source text for a mock Chinese layout test. "
        "The content at https://example.org/paper should remain inside the original column "
        "after replacement and finish in 10 ms.",
        fontsize=9,
        fontname="tiro",
    )
    page.insert_textbox(
        pymupdf.Rect(230, 120, 380, 360),
        "A second column checks that the renderer preserves the original page geometry and links.",
        fontsize=9,
        fontname="tiro",
    )
    document.save(path)
    document.close()


def test_mock_translation_pipeline_creates_cjk_pdf_and_layout_report(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    output_dir = tmp_path / "mock"
    _create_mock_fixture(source)

    result = run_mock_translation(source, output_dir)

    assert result.output_pdf.is_file()
    assert result.protected_segments_json.is_file()
    assert result.provider_run_json.is_file()
    assert result.translations_json.is_file()
    assert result.layout_json.is_file()
    assert result.report_json.is_file()
    assert result.report["provider"] == "mock"
    assert result.report["layout"]["overflow_flow_count"] == 0
    assert result.report["render"]["rendered_lines"] > 0
    assert result.report["protection"]["token_count"] == 2
    assert result.report["protection"]["passed"] is True
    assert result.report["provider_execution"]["failure_count"] == 0
    with pymupdf.open(result.output_pdf) as output_pdf:
        text = "".join(page.get_text() for page in output_pdf)
    assert any("\u4e00" <= character <= "\u9fff" for character in text)

import json
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient

from papertrans.desktop.api import create_desktop_api
from papertrans.desktop.jobs import DesktopJobManager, DesktopJobRequest
from papertrans.desktop.reading_map import build_reading_map


def _write_reading_artifacts(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "document.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "number": 1,
                        "width": 612,
                        "height": 792,
                        "regions": [
                            {
                                "id": "p1-r1",
                                "bbox": [40, 80, 280, 120],
                            },
                            {
                                "id": "p1-protected",
                                "bbox": [40, 130, 280, 150],
                            },
                        ],
                    }
                ],
                "text_flows": [
                    {
                        "id": "flow-1",
                        "type": "paragraph",
                        "region_ids": ["p1-r1"],
                        "source_text": "Source paragraph.",
                        "translatable": True,
                    },
                    {
                        "id": "flow-protected",
                        "type": "formula",
                        "region_ids": ["p1-protected"],
                        "source_text": "x = 1",
                        "translatable": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "layout.json").write_text(
        json.dumps(
            {
                "font_path": "missing-normal-font.ttf",
                "bold_font_path": "missing-bold-font.ttf",
                "flows": [
                    {
                        "flow_id": "flow-1",
                        "variant": "compact",
                        "placements": [
                            {
                                "page_number": 1,
                                "text": "译文。",
                                "x": 40,
                                "baseline_y": 100,
                                "font_size": 10,
                                "bold": False,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "translations.json").write_text(
        json.dumps(
            {
                "translations": [
                    {
                        "segment_id": "flow-1",
                        "normal": "较长的译文。",
                        "compact": "译文。",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _pdf_bytes() -> bytes:
    document = pymupdf.open()
    document.new_page(width=612, height=792)
    payload = document.tobytes()
    document.close()
    return payload


def test_reading_map_uses_stable_flow_ids_and_actual_layout_variant(tmp_path: Path) -> None:
    _write_reading_artifacts(tmp_path)

    result = build_reading_map(tmp_path, 1)

    assert result["schemaVersion"] == "m7_reading_map_v1"
    assert result["page"] == {"number": 1, "width": 612.0, "height": 792.0}
    assert len(result["paragraphs"]) == 1
    paragraph = result["paragraphs"][0]
    assert paragraph["id"] == "flow-1"
    assert paragraph["sourceText"] == "Source paragraph."
    assert paragraph["translation"] == "译文。"
    assert paragraph["sourcePageNumbers"] == [1]
    assert paragraph["translationPageNumbers"] == [1]
    assert paragraph["sourceBoxes"] == [[40.0, 80.0, 280.0, 120.0]]
    assert paragraph["translationBoxes"][0][0] == 40.0
    assert paragraph["translationBoxes"][0][2] > 40.0
    assert "font_path" not in json.dumps(result)


def test_reading_map_rejects_pages_outside_the_document(tmp_path: Path) -> None:
    _write_reading_artifacts(tmp_path)

    with pytest.raises(ValueError, match="页码超出文档范围"):
        build_reading_map(tmp_path, 2)


def test_desktop_reading_map_endpoint_is_token_protected(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(_pdf_bytes())

    def runner(source_path, output_dir, provider, **kwargs):  # type: ignore[no-untyped-def]
        resolved = Path(output_dir)
        _write_reading_artifacts(resolved)
        output = resolved / "output.pdf"
        output.write_bytes(_pdf_bytes())
        return SimpleNamespace(
            output_dir=resolved,
            output_pdf=output,
            report={"passed": True, "layout": {}, "layout_safety": {"counts": {}}},
        )

    manager = DesktopJobManager(
        tmp_path / "jobs",
        provider_factory=lambda *args, **kwargs: SimpleNamespace(name="mock"),
        runner=runner,
    )
    started = manager.start(DesktopJobRequest(source, tmp_path / "out"))
    manager.wait(started["id"])
    client = TestClient(create_desktop_api(manager, session_token="test-session"))
    url = f"/api/jobs/{started['id']}/reading-map/1"

    assert client.get(url).status_code == 401
    response = client.get(url, headers={"X-PaperTrans-Token": "test-session"})

    assert response.status_code == 200
    assert response.json()["paragraphs"][0]["id"] == "flow-1"
    library_map = client.get(
        f"/api/library/tasks/{started['id']}/reading-map/1",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert library_map.status_code == 200
    assert library_map.json()["paragraphs"][0]["translationPageNumbers"] == [1]
    for kind in ("source", "output"):
        artifact = client.get(
            f"/api/library/tasks/{started['id']}/{kind}",
            headers={"X-PaperTrans-Token": "test-session"},
        )
        assert artifact.status_code == 200
        assert artifact.headers["content-type"] == "application/pdf"
    manager.shutdown()

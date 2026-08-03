from pathlib import Path
from types import SimpleNamespace

import pymupdf
from fastapi.testclient import TestClient

from papertrans.desktop.api import create_desktop_api
from papertrans.desktop.jobs import DesktopJobManager, DesktopJobRequest


def _pdf_bytes() -> bytes:
    document = pymupdf.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


def test_desktop_api_requires_session_and_accepts_pdf_upload(tmp_path: Path) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    app = create_desktop_api(manager, session_token="test-session")
    client = TestClient(app)

    assert client.get("/api/system").status_code == 401
    response = client.post(
        "/api/uploads",
        headers={"X-PaperTrans-Token": "test-session"},
        files={"file": ("paper.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "paper.pdf"
    assert response.json()["pageCount"] == 1
    assert response.json()["id"]

    preview = client.get(
        f"/api/sources/{response.json()['id']}",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-disposition"].startswith("inline;")
    manager.shutdown()


def test_desktop_api_registers_native_pdf_for_preview(tmp_path: Path) -> None:
    source = tmp_path / "native-paper.pdf"
    source.write_bytes(_pdf_bytes())
    manager = DesktopJobManager(tmp_path / "jobs")
    client = TestClient(
        create_desktop_api(manager, session_token="test-session")
    )

    response = client.post(
        "/api/sources",
        headers={"X-PaperTrans-Token": "test-session"},
        json={"path": str(source)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == source.name
    assert payload["id"]
    preview = client.get(
        f"/api/sources/{payload['id']}",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert preview.content == source.read_bytes()
    manager.shutdown()


def test_system_info_reports_ocr_only_when_local_model_directory_exists(
    tmp_path: Path,
) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    app = create_desktop_api(
        manager, session_token="test-session", ocr_model_dir=model_dir
    )
    response = TestClient(app).get(
        "/api/system", headers={"X-PaperTrans-Token": "test-session"}
    )

    assert response.status_code == 200
    assert response.json()["ocr"]["ready"] is True
    assert response.json()["providers"][-1]["name"] == "mock"
    manager.shutdown()


def test_pdf_artifacts_are_served_inline_for_the_desktop_viewer(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(_pdf_bytes())

    def runner(source_path, output_dir, provider, **kwargs):  # type: ignore[no-untyped-def]
        resolved = Path(output_dir)
        resolved.mkdir(parents=True)
        output = resolved / "output.pdf"
        output.write_bytes(_pdf_bytes())
        return SimpleNamespace(
            output_dir=resolved,
            output_pdf=output,
            report={
                "passed": True,
                "layout": {},
                "layout_safety": {"counts": {}},
            },
        )

    manager = DesktopJobManager(
        tmp_path / "jobs",
        provider_factory=lambda *args, **kwargs: SimpleNamespace(name="mock"),
        runner=runner,
    )
    started = manager.start(
        DesktopJobRequest(source, tmp_path / "out", provider="mock")
    )
    manager.wait(started["id"])
    client = TestClient(create_desktop_api(manager, session_token="test-session"))

    for kind in ("source", "output"):
        response = client.get(
            f"/api/jobs/{started['id']}/{kind}",
            headers={"X-PaperTrans-Token": "test-session"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"].startswith("inline;")

    manager.shutdown()

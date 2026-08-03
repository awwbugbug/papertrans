from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from papertrans.desktop.api import create_desktop_api
from papertrans.desktop.jobs import DesktopJobManager


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

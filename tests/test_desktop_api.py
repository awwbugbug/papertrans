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
    uploaded_path = Path(response.json()["path"])
    unauthorized_release = client.delete(f"/api/sources/{response.json()['id']}")
    released = client.delete(
        f"/api/sources/{response.json()['id']}",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert unauthorized_release.status_code == 401
    assert released.json() == {"released": True}
    assert not uploaded_path.parent.exists()
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


def test_pdf_artifacts_are_served_inline_for_the_desktop_viewer(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
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

    opened: list[Path] = []
    monkeypatch.setattr("os.startfile", lambda path: opened.append(Path(path)))
    response = client.post(
        f"/api/jobs/{started['id']}/open",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert response.json() == {"opened": True}
    assert opened == [manager.output_dir(started["id"])]

    manager.shutdown()


def test_tauri_origin_can_preflight_the_authenticated_api(tmp_path: Path) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    client = TestClient(create_desktop_api(manager, session_token="test-session"))

    response = client.options(
        "/api/system",
        headers={
            "Origin": "http://localhost:1420",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-PaperTrans-Token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:1420"
    manager.shutdown()


def test_desktop_api_translates_plain_text_through_protected_mock_path(
    tmp_path: Path,
) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    client = TestClient(create_desktop_api(manager, session_token="test-session"))

    unauthorized = client.post(
        "/api/text-translations",
        json={"text": "See [7] in 10 ms.", "provider": "mock"},
    )
    response = client.post(
        "/api/text-translations",
        headers={"X-PaperTrans-Token": "test-session"},
        json={"text": "See [7] in 10 ms.", "provider": "mock"},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert "[7]" in payload["translation"]
    assert "10 ms" in payload["translation"]
    assert payload["protection"]["passed"] is True
    assert payload["task"]["kind"] == "text"

    listing = client.get(
        "/api/library/tasks",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    detail = client.get(
        f"/api/library/tasks/{payload['task']['id']}",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert listing.json()["tasks"] == [payload["task"]]
    assert detail.json()["sourceText"] == "See [7] in 10 ms."
    assert detail.json()["translation"] == payload["translation"]
    unauthorized_delete = client.delete(f"/api/library/tasks/{payload['task']['id']}")
    deleted = client.delete(
        f"/api/library/tasks/{payload['task']['id']}",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert unauthorized_delete.status_code == 401
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["internalFilesRemoved"] is True
    assert client.get(
        "/api/library/tasks",
        headers={"X-PaperTrans-Token": "test-session"},
    ).json() == {"tasks": []}
    manager.shutdown()


def test_desktop_api_reports_and_clears_only_translation_cache(tmp_path: Path) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    cache_file = tmp_path / "cache" / "deepseek" / "aa" / "entry.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"cached")
    source = tmp_path / "original.pdf"
    source.write_bytes(_pdf_bytes())
    client = TestClient(create_desktop_api(manager, session_token="test-session"))
    headers = {"X-PaperTrans-Token": "test-session"}

    info = client.get("/api/storage", headers=headers)
    cleared = client.post("/api/storage/cache/clear", headers=headers)

    assert info.status_code == 200
    assert info.json()["cache"] == {"fileCount": 1, "bytes": len(b"cached")}
    assert cleared.status_code == 200
    assert cleared.json()["removed"] == info.json()["cache"]
    assert cleared.json()["storage"]["cache"] == {"fileCount": 0, "bytes": 0}
    assert source.is_file()
    manager.shutdown()


def test_desktop_api_translates_selection_without_creating_library_history(
    tmp_path: Path,
) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    client = TestClient(create_desktop_api(manager, session_token="test-session"))

    unauthorized = client.post(
        "/api/selection-translations",
        json={"text": "proposal [4]", "provider": "mock"},
    )
    response = client.post(
        "/api/selection-translations",
        headers={"X-PaperTrans-Token": "test-session"},
        json={"text": "proposal [4]", "provider": "mock"},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "m7_selection_translation_v1"
    assert payload["provider"] == "mock"
    assert "[4]" in payload["translation"]
    assert payload["characterCount"] == len("proposal [4]")
    assert "task" not in payload
    listing = client.get(
        "/api/library/tasks",
        headers={"X-PaperTrans-Token": "test-session"},
    )
    assert listing.json() == {"tasks": []}
    manager.shutdown()


def test_desktop_api_rejects_oversized_selected_text(tmp_path: Path) -> None:
    manager = DesktopJobManager(tmp_path / "jobs")
    client = TestClient(create_desktop_api(manager, session_token="test-session"))

    response = client.post(
        "/api/selection-translations",
        headers={"X-PaperTrans-Token": "test-session"},
        json={"text": "x" * 301, "provider": "mock"},
    )

    assert response.status_code == 422
    assert manager.library.list_tasks() == []
    manager.shutdown()

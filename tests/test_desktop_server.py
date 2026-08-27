from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from papertrans.desktop import server


def test_desktop_server_disables_console_dependent_uvicorn_logging(
    monkeypatch: Any, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: object, **options: object) -> None:
        captured["app"] = app
        captured.update(options)

    monkeypatch.setattr(server.uvicorn, "run", fake_run)
    monkeypatch.setattr(server, "create_desktop_api", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "papertrans-sidecar",
            "--port",
            "1421",
            "--token",
            "test-token",
            "--data-root",
            str(tmp_path),
        ],
    )

    server.main()

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 1421
    assert captured["log_config"] is None
    assert captured["access_log"] is False

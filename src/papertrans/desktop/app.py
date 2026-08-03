from __future__ import annotations

import os
import secrets
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pymupdf
import uvicorn

from papertrans.desktop.api import create_desktop_api
from papertrans.desktop.jobs import DesktopJobManager
from papertrans.desktop.windowing import DesktopWindowFrame


class DesktopBridge:
    def __init__(
        self,
        manager: DesktopJobManager,
        *,
        frame_controller: DesktopWindowFrame | None = None,
    ) -> None:
        self._manager = manager
        self._window: Any | None = None
        self._maximized = False
        self._frame = frame_controller or DesktopWindowFrame()

    def attach(self, window: Any) -> None:
        self._window = window
        self._frame.attach(window)

    def initialize_window_frame(self) -> bool:
        return self._frame.initialize()

    def begin_window_drag(self) -> bool:
        return self._frame.begin_move()

    def begin_window_resize(self, edge: str) -> bool:
        return self._frame.begin_resize(edge)

    def pick_pdf(self) -> dict[str, object] | None:
        import webview

        if self._window is None:
            return None
        selected = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("PDF files (*.pdf)",),
        )
        if not selected:
            return None
        path = Path(selected[0]).resolve()
        with pymupdf.open(path) as document:
            page_count = len(document)
        return {
            "path": str(path),
            "name": path.name,
            "size": path.stat().st_size,
            "pageCount": page_count,
        }

    def pick_directory(self) -> str | None:
        import webview

        if self._window is None:
            return None
        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return str(Path(selected[0]).resolve()) if selected else None

    def open_output(self, job_id: str) -> bool:
        path = self._manager.output_dir(job_id)
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        return False

    def minimize_window(self) -> bool:
        if self._window is None:
            return False
        self._window.minimize()
        return True

    def toggle_maximize_window(self) -> bool:
        if self._window is None:
            return False
        if self._maximized:
            self._window.restore()
            self._maximized = False
        else:
            self._window.maximize()
            self._maximized = True
        self._frame.set_maximized(self._maximized)
        return self._maximized

    def set_window_state(self, maximized: bool) -> None:
        self._maximized = maximized
        self._frame.set_maximized(maximized)
        if self._window is not None:
            self._window.evaluate_js(
                "window.dispatchEvent(new CustomEvent('papertrans-window-state', "
                f"{{detail: {{maximized: {str(maximized).lower()}}}}}));"
            )

    def close_window(self) -> bool:
        if self._window is None:
            return False
        self._window.destroy()
        return True


def main() -> None:
    import webview

    repository = _repository_root()
    jobs_root = repository / ".papertrans" / "jobs"
    model_root = repository / "models" / "paddleocr"
    frontend = repository / "frontend" / "dist" / "client"
    if not (frontend / "index.html").is_file():
        raise RuntimeError("Desktop frontend is not built; run the frontend build first")

    token = secrets.token_urlsafe(32)
    manager = DesktopJobManager(jobs_root)
    app = create_desktop_api(
        manager,
        session_token=token,
        frontend_dir=frontend,
        ocr_model_dir=model_root,
    )
    port = _available_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, name="papertrans-api", daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("PaperTrans local service failed to start")

    bridge = DesktopBridge(manager)
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    window = webview.create_window(
        "PaperTrans",
        f"http://127.0.0.1:{port}/?session={token}",
        js_api=bridge,
        width=1440,
        height=900,
        min_size=(1080, 720),
        frameless=True,
        easy_drag=False,
        shadow=True,
        background_color="#faf9fe",
    )
    bridge.attach(window)
    window.events.shown += bridge.initialize_window_frame
    window.events.maximized += lambda: bridge.set_window_state(True)
    window.events.restored += lambda: bridge.set_window_state(False)
    try:
        webview.start(gui="edgechromium")
    finally:
        server.should_exit = True
        manager.shutdown()


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]

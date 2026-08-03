from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from papertrans.desktop.api import create_desktop_api
from papertrans.desktop.jobs import DesktopJobManager


def main() -> None:
    arguments = _parser().parse_args()
    repository = Path(arguments.repository).resolve()
    manager = DesktopJobManager(repository / ".papertrans" / "jobs")
    app = create_desktop_api(
        manager,
        session_token=arguments.token,
        ocr_model_dir=repository / "models" / "paddleocr",
    )
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=arguments.port,
            log_level="warning",
            access_log=False,
        )
    finally:
        manager.shutdown()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaperTrans local desktop service")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--token", required=True)
    parser.add_argument("--repository", required=True)
    return parser


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from papertrans.desktop.api import create_desktop_api
from papertrans.desktop.jobs import DesktopJobManager


def main() -> None:
    arguments = _parser().parse_args()
    repository = Path(arguments.repository).resolve() if arguments.repository else None
    data_root = (
        Path(arguments.data_root).expanduser().resolve()
        if arguments.data_root
        else repository / ".papertrans"
        if repository is not None
        else None
    )
    if data_root is None:
        raise SystemExit("either --repository or --data-root is required")
    data_root.mkdir(parents=True, exist_ok=True)
    if arguments.ocr_model_dir:
        ocr_model_dir = Path(arguments.ocr_model_dir).expanduser().resolve()
    elif repository is not None:
        ocr_model_dir = repository / "models" / "paddleocr"
    else:
        ocr_model_dir = data_root / "models" / "paddleocr"
    manager = DesktopJobManager(data_root / "jobs")
    app = create_desktop_api(
        manager,
        session_token=arguments.token,
        ocr_model_dir=ocr_model_dir,
    )
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=arguments.port,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
    finally:
        manager.shutdown()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaperTrans local desktop service")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--token", required=True)
    parser.add_argument("--repository")
    parser.add_argument("--data-root")
    parser.add_argument("--ocr-model-dir")
    return parser


if __name__ == "__main__":
    main()

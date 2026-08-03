from __future__ import annotations

import os
import secrets
import shutil
import threading
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from papertrans.desktop.jobs import DesktopJobManager, DesktopJobRequest, inspect_source
from papertrans.translation.profiles import DEEPSEEK_PROFILE, KIMI_PROFILE

MAX_UPLOAD_BYTES = 250 * 1024 * 1024


class StartJobPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_path: str = Field(alias="sourcePath")
    output_dir: str = Field(alias="outputDir")
    provider: str
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None
    base_url: str | None = Field(default=None, alias="baseUrl")
    ocr_enabled: bool = Field(default=False, alias="ocrEnabled")
    ocr_model_dir: str | None = Field(default=None, alias="ocrModelDir")


class RegisterSourcePayload(BaseModel):
    path: str


def create_desktop_api(
    manager: DesktopJobManager,
    *,
    session_token: str | None = None,
    uploads_dir: str | Path | None = None,
    frontend_dir: str | Path | None = None,
    ocr_model_dir: str | Path | None = None,
) -> FastAPI:
    token = session_token or secrets.token_urlsafe(32)
    upload_root = Path(uploads_dir or manager.jobs_root / "uploads").resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    model_root = Path(ocr_model_dir).resolve() if ocr_model_dir is not None else None

    app = FastAPI(title="PaperTrans Desktop API", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-PaperTrans-Token", "Content-Type"],
    )
    app.state.session_token = token
    app.state.manager = manager
    sources: dict[str, Path] = {}
    sources_lock = threading.Lock()

    def register_source(path: str | Path) -> dict[str, object]:
        resolved = Path(path).expanduser().resolve()
        metadata = inspect_source(resolved)
        source_id = uuid4().hex
        with sources_lock:
            sources[source_id] = resolved
        return {"id": source_id, **metadata}

    @app.middleware("http")
    async def require_session(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method != "OPTIONS" and request.url.path.startswith("/api/"):
            supplied = request.headers.get("X-PaperTrans-Token") or request.query_params.get(
                "session"
            )
            if not supplied or not secrets.compare_digest(supplied, token):
                return _unauthorized_response()
        return await call_next(request)

    @app.get("/api/system")
    def system_info() -> dict[str, object]:
        return {
            "providers": [
                {
                    "name": "deepseek",
                    "label": "DeepSeek",
                    "defaultModel": DEEPSEEK_PROFILE.default_model,
                    "requiresApiKey": True,
                },
                {
                    "name": "kimi",
                    "label": "Kimi",
                    "defaultModel": KIMI_PROFILE.default_model,
                    "requiresApiKey": True,
                },
                {
                    "name": "compatible",
                    "label": "兼容接口",
                    "defaultModel": None,
                    "requiresApiKey": True,
                },
                {
                    "name": "mock",
                    "label": "Mock 版式测试",
                    "defaultModel": None,
                    "requiresApiKey": False,
                },
            ],
            "ocr": {
                "ready": bool(model_root and model_root.is_dir()),
                "modelDir": str(model_root) if model_root and model_root.is_dir() else None,
            },
            "defaultOutputDir": str(manager.jobs_root),
        }

    @app.post("/api/uploads")
    async def upload_pdf(
        file: Annotated[UploadFile, File(description="PDF document")],
    ) -> dict[str, object]:
        filename = Path(file.filename or "document.pdf").name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="请选择 PDF 文件")
        destination_dir = upload_root / uuid4().hex
        destination_dir.mkdir(parents=True)
        destination = destination_dir / filename
        size = 0
        try:
            with destination.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="PDF 不能超过 250 MB")
                    output.write(chunk)
            return register_source(destination)
        except Exception:
            shutil.rmtree(destination_dir, ignore_errors=True)
            raise
        finally:
            await file.close()

    @app.post("/api/sources")
    def register_native_source(payload: RegisterSourcePayload) -> dict[str, object]:
        try:
            return register_source(payload.path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sources/{source_id}")
    def preview_source(source_id: str) -> FileResponse:
        with sources_lock:
            path = sources.get(source_id)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="源 PDF 不存在")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    @app.post("/api/jobs")
    def start_job(payload: StartJobPayload) -> dict[str, object]:
        try:
            return manager.start(
                DesktopJobRequest(
                    source_path=Path(payload.source_path),
                    output_dir=Path(payload.output_dir),
                    provider=payload.provider,
                    model=payload.model,
                    base_url=payload.base_url,
                    ocr_enabled=payload.ocr_enabled,
                    ocr_model_dir=(
                        Path(payload.ocr_model_dir) if payload.ocr_model_dir else None
                    ),
                ),
                api_key=payload.api_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return manager.snapshot(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc

    @app.get("/api/jobs/{job_id}/source")
    def source_pdf(job_id: str) -> FileResponse:
        try:
            path = manager.source_path(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    @app.get("/api/jobs/{job_id}/output")
    def output_pdf(job_id: str) -> FileResponse:
        try:
            path = manager.output_pdf(job_id)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="译文 PDF 尚不可用") from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    @app.post("/api/jobs/{job_id}/open")
    def open_job_output(job_id: str) -> dict[str, bool]:
        try:
            path = manager.output_dir(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            raise HTTPException(status_code=501, detail="当前平台暂不支持打开文件夹")
        os.startfile(path)  # type: ignore[attr-defined]
        return {"opened": True}

    if frontend_dir is not None:
        static_root = Path(frontend_dir).resolve()
        if static_root.is_dir():
            app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")
    return app


def _unauthorized_response():
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=401, content={"detail": "Desktop session required"})

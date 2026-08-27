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
from papertrans.desktop.reading_map import build_reading_map
from papertrans.desktop.storage import DesktopStorageManager
from papertrans.desktop.text_translation import (
    MAX_SELECTED_TRANSLATION_CHARS,
    MAX_TEXT_TRANSLATION_CHARS,
    TEXT_TRANSLATION_MODE_SELECTION,
    DesktopTextTranslationRequest,
    DesktopTextTranslator,
)
from papertrans.translation.models import list_provider_models
from papertrans.translation.profiles import DEEPSEEK_PROFILE, KIMI_PROFILE, ZHIPU_PROFILE

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
    target_language: str = Field(default="zh-CN", alias="targetLanguage")


class ProviderModelsPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    api_key: str | None = Field(default=None, alias="apiKey")
    base_url: str | None = Field(default=None, alias="baseUrl")


class RegisterSourcePayload(BaseModel):
    path: str


class TranslateTextPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(max_length=MAX_TEXT_TRANSLATION_CHARS)
    provider: str
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None
    base_url: str | None = Field(default=None, alias="baseUrl")
    source_language: str = Field(default="auto", alias="sourceLanguage")
    target_language: str = Field(default="zh-CN", alias="targetLanguage")


class TranslateSelectionPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(max_length=MAX_SELECTED_TRANSLATION_CHARS)
    provider: str
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None
    base_url: str | None = Field(default=None, alias="baseUrl")
    source_language: str = Field(default="auto", alias="sourceLanguage")
    target_language: str = Field(default="zh-CN", alias="targetLanguage")


def create_desktop_api(
    manager: DesktopJobManager,
    *,
    session_token: str | None = None,
    uploads_dir: str | Path | None = None,
    frontend_dir: str | Path | None = None,
    ocr_model_dir: str | Path | None = None,
    text_translator: DesktopTextTranslator | None = None,
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
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["X-PaperTrans-Token", "Content-Type"],
    )
    app.state.session_token = token
    app.state.manager = manager
    app.state.text_translator = text_translator or DesktopTextTranslator(
        manager.jobs_root.parent / "cache" / "text"
    )
    app.state.storage = DesktopStorageManager(manager.jobs_root.parent, upload_root)
    storage_lock = threading.Lock()
    sources: dict[str, Path] = {}
    sources_lock = threading.Lock()

    def retained_source_paths() -> set[Path]:
        retained = manager.library.source_paths() | manager.active_source_paths()
        with sources_lock:
            retained.update(sources.values())
        return retained

    def best_effort_orphan_cleanup() -> None:
        try:
            app.state.storage.clear_orphan_uploads(retained_source_paths())
        except OSError:
            # A locked temporary file must not prevent startup or undo a completed user action.
            pass

    best_effort_orphan_cleanup()

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
                    "name": "zhipu",
                    "label": "智谱AI",
                    "defaultModel": ZHIPU_PROFILE.default_model,
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

    @app.delete("/api/sources/{source_id}")
    def release_source(source_id: str) -> dict[str, bool]:
        with sources_lock:
            released = sources.pop(source_id, None) is not None
        best_effort_orphan_cleanup()
        return {"released": released}

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
                    target_language=payload.target_language,
                ),
                api_key=payload.api_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/provider-models")
    def provider_models(payload: ProviderModelsPayload) -> dict[str, object]:
        try:
            models = list_provider_models(
                payload.provider,
                payload.api_key or "",
                payload.base_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"models": models}

    @app.post("/api/text-translations")
    def translate_text(payload: TranslateTextPayload) -> dict[str, object]:
        try:
            with storage_lock:
                result = app.state.text_translator.translate(
                    DesktopTextTranslationRequest(
                        text=payload.text,
                        provider=payload.provider,
                        model=payload.model,
                        base_url=payload.base_url,
                        source_language=payload.source_language,
                        target_language=payload.target_language,
                    ),
                    api_key=payload.api_key,
                )
            result["task"] = manager.library.add_text_task(
                source_text=payload.text,
                translation=str(result["translation"]),
                provider=payload.provider,
            )
            return result
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=_safe_text_translation_error(exc, payload.api_key),
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail=_safe_text_translation_error(exc, payload.api_key),
            ) from exc

    @app.post("/api/selection-translations")
    def translate_selection(payload: TranslateSelectionPayload) -> dict[str, object]:
        try:
            with storage_lock:
                result = app.state.text_translator.translate(
                    DesktopTextTranslationRequest(
                        text=payload.text,
                        provider=payload.provider,
                        model=payload.model,
                        base_url=payload.base_url,
                        source_language=payload.source_language,
                        target_language=payload.target_language,
                        translation_mode=TEXT_TRANSLATION_MODE_SELECTION,
                    ),
                    api_key=payload.api_key,
                )
            return {"schema": "m7_selection_translation_v1", **result}
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=_safe_text_translation_error(exc, payload.api_key),
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail=_safe_text_translation_error(exc, payload.api_key),
            ) from exc

    @app.get("/api/library/tasks")
    def list_library_tasks() -> dict[str, object]:
        return {"tasks": manager.library.list_tasks()}

    @app.get("/api/library/tasks/{task_id}")
    def get_library_task(task_id: str) -> dict[str, object]:
        try:
            return manager.library.get_task(task_id)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="本地任务不存在或内容不可用") from exc

    @app.delete("/api/library/tasks/{task_id}")
    def delete_library_task(task_id: str) -> dict[str, object]:
        try:
            deleted = manager.delete_library_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="本地任务不存在") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        best_effort_orphan_cleanup()
        return {"deleted": True, **deleted}

    @app.get("/api/storage")
    def storage_info() -> dict[str, object]:
        return app.state.storage.snapshot()

    @app.post("/api/storage/cache/clear")
    def clear_translation_cache() -> dict[str, object]:
        try:
            with storage_lock:
                return manager.run_storage_maintenance(app.state.storage.clear_cache)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/storage/uploads/clear")
    def clear_temporary_uploads() -> dict[str, object]:
        return app.state.storage.clear_orphan_uploads(retained_source_paths())

    @app.get("/api/library/tasks/{task_id}/{kind}")
    def library_pdf_artifact(task_id: str, kind: str) -> FileResponse:
        if kind not in {"source", "output"}:
            raise HTTPException(status_code=404, detail="PDF 文件不存在")
        try:
            path = manager.library.pdf_artifact(task_id, kind)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="PDF 文件不存在") from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
        )

    @app.get("/api/library/tasks/{task_id}/reading-map/{page_number}")
    def library_reading_map(task_id: str, page_number: int) -> dict[str, object]:
        try:
            return build_reading_map(manager.library.pdf_output_dir(task_id), page_number)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="段落映射尚不可用") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/library/tasks/{task_id}/open")
    def open_library_task(task_id: str) -> dict[str, bool]:
        try:
            path = manager.library.open_path(task_id)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="本地任务不存在或内容不可用") from exc
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            raise HTTPException(status_code=501, detail="当前平台暂不支持打开文件夹")
        os.startfile(path)  # type: ignore[attr-defined]
        return {"opened": True}

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

    @app.get("/api/jobs/{job_id}/reading-map/{page_number}")
    def reading_map(job_id: str, page_number: int) -> dict[str, object]:
        try:
            return manager.reading_map(job_id, page_number)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="段落映射尚不可用") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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


def _safe_text_translation_error(exc: Exception, secret: str | None) -> str:
    message = str(exc)
    if secret:
        message = message.replace(secret, "[REDACTED]")
    if not message or "sk-" in message.lower() or "bearer " in message.lower():
        return "文本翻译失败，请检查服务配置"
    return message[:300]

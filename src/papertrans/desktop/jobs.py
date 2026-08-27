from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf

from papertrans.desktop.library import LocalTaskLibrary
from papertrans.desktop.reading_map import build_reading_map
from papertrans.ingest import OCRPreflightError, OCRRuntimeConfig
from papertrans.translation import (
    CloseableTranslationProvider,
    TranslationProvider,
    create_translation_provider,
)
from papertrans.translation_job import TranslationJobResult, run_translation_job

ProviderFactory = Callable[..., TranslationProvider]
JobRunner = Callable[..., TranslationJobResult]

DESKTOP_PROVIDER_LABELS = {
    "mock": "Mock 版式测试",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "zhipu": "智谱AI",
    "compatible": "兼容接口",
}
DESKTOP_PROVIDER_KEY_NAMES = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "zhipu": "ZHIPUAI_API_KEY",
    "compatible": "PAPERTRANS_COMPATIBLE_API_KEY",
}


@dataclass(frozen=True, slots=True)
class DesktopJobRequest:
    source_path: Path
    output_dir: Path
    provider: str = "mock"
    model: str | None = None
    base_url: str | None = None
    ocr_enabled: bool = False
    ocr_model_dir: Path | None = None
    target_language: str = "zh-CN"


@dataclass(slots=True)
class _JobRecord:
    id: str
    request: DesktopJobRequest
    source_name: str
    created_at: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "任务已进入本地队列"
    output_dir: Path | None = None
    output_pdf: Path | None = None
    report: dict[str, Any] | None = None
    future: Future[None] | None = field(default=None, repr=False)


class DesktopJobManager:
    def __init__(
        self,
        jobs_root: str | Path,
        *,
        provider_factory: ProviderFactory = create_translation_provider,
        runner: JobRunner = run_translation_job,
        library: LocalTaskLibrary | None = None,
    ) -> None:
        self.jobs_root = Path(jobs_root).expanduser().resolve()
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._provider_factory = provider_factory
        self._runner = runner
        self.library = library or LocalTaskLibrary(self.jobs_root.parent / "library")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="papertrans-job")
        self._jobs: dict[str, _JobRecord] = {}
        self._lock = threading.Lock()

    def start(self, request: DesktopJobRequest, *, api_key: str | None = None) -> dict[str, Any]:
        resolved = self._validate_request(request, api_key)
        job_id = uuid4().hex
        record = _JobRecord(
            id=job_id,
            request=resolved,
            source_name=resolved.source_path.name,
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._jobs[job_id] = record
            self.library.create_pdf_task(
                task_id=job_id,
                source_path=resolved.source_path,
                output_dir=resolved.output_dir,
                provider=resolved.provider,
                created_at=record.created_at,
            )
            record.future = self._executor.submit(self._execute, job_id, api_key)
        return self.snapshot(job_id)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._require(job_id)
            report = _public_report(record.report)
            return {
                "id": record.id,
                "status": record.status,
                "stage": record.stage,
                "sourceName": record.source_name,
                "provider": record.request.provider,
                "message": record.message,
                "createdAt": record.created_at,
                "outputAvailable": bool(record.output_pdf and record.output_pdf.is_file()),
                "report": report,
            }

    def source_path(self, job_id: str) -> Path:
        with self._lock:
            return self._require(job_id).request.source_path

    def output_pdf(self, job_id: str) -> Path:
        with self._lock:
            record = self._require(job_id)
            if record.output_pdf is None or not record.output_pdf.is_file():
                raise FileNotFoundError("Translated PDF is not available")
            return record.output_pdf

    def output_dir(self, job_id: str) -> Path:
        with self._lock:
            record = self._require(job_id)
            return record.output_dir or record.request.output_dir

    def reading_map(self, job_id: str, page_number: int) -> dict[str, Any]:
        with self._lock:
            record = self._require(job_id)
            if record.output_pdf is None or not record.output_pdf.is_file():
                raise FileNotFoundError("Translated PDF is not available")
            output_dir = record.output_dir
        assert output_dir is not None
        return build_reading_map(output_dir, page_number)

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
        with self._lock:
            future = self._require(job_id).future
        if future is not None:
            future.result(timeout=timeout)
        return self.snapshot(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def delete_library_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._jobs.get(task_id)
            if record is not None and record.future is not None and not record.future.done():
                raise RuntimeError("任务正在运行，完成后才能删除")
            deleted = self.library.delete_task(task_id)
            self._jobs.pop(task_id, None)
            return deleted

    def active_source_paths(self) -> set[Path]:
        with self._lock:
            return {
                record.request.source_path
                for record in self._jobs.values()
                if record.future is not None and not record.future.done()
            }

    def run_storage_maintenance(self, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            if any(
                record.future is not None and not record.future.done()
                for record in self._jobs.values()
            ):
                raise RuntimeError("翻译任务运行期间不能清理缓存")
            return action()

    def _execute(self, job_id: str, api_key: str | None) -> None:
        with self._lock:
            record = self._require(job_id)
            record.status = "running"
            record.stage = "pipeline"
            record.message = "正在执行解析、翻译、排版和质量检查"
            request = record.request
            intended_output = request.output_dir / (
                f"{request.source_path.stem}-{request.provider}-translation"
            )
            record.output_dir = intended_output
            self._persist_pdf_record(record)

        provider: TranslationProvider | None = None
        try:
            environment = self._credential_environment(request.provider, api_key)
            provider = self._provider_factory(
                request.provider,
                model=request.model,
                base_url=request.base_url,
                environ=environment,
            )
            output_dir = intended_output
            ocr_config = None
            if request.ocr_enabled:
                assert request.ocr_model_dir is not None
                ocr_config = OCRRuntimeConfig(
                    backend="paddleocr", model_dir=request.ocr_model_dir
                )
            result = self._runner(
                request.source_path,
                output_dir,
                provider,
                ocr_config=ocr_config,
                target_language=request.target_language,
            )
            with self._lock:
                record = self._require(job_id)
                record.output_dir = result.output_dir
                record.output_pdf = result.output_pdf if result.output_pdf.is_file() else None
                record.report = result.report
                record.status = "completed" if result.report.get("passed") else "review"
                record.stage = "completed"
                record.message = (
                    "翻译 PDF 已通过质量检查"
                    if record.status == "completed"
                    else "翻译结果需要人工检查"
                )
                self._persist_pdf_record(record)
        except OCRPreflightError:
            with self._lock:
                record = self._require(job_id)
                record.status = "review"
                record.stage = "ocr_review"
                record.message = "部分页面需要开启 OCR 或人工检查"
                self._persist_pdf_record(record)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            with self._lock:
                record = self._require(job_id)
                record.status = "failed"
                record.stage = "failed"
                record.message = _safe_error_message(exc, secret=api_key)
                self._persist_pdf_record(record)
        except Exception:
            with self._lock:
                record = self._require(job_id)
                record.status = "failed"
                record.stage = "failed"
                record.message = "本地任务执行失败，请查看诊断信息"
                self._persist_pdf_record(record)
        finally:
            if isinstance(provider, CloseableTranslationProvider):
                try:
                    provider.close()
                except Exception:
                    pass

    def _validate_request(
        self, request: DesktopJobRequest, api_key: str | None
    ) -> DesktopJobRequest:
        source = request.source_path.expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError("请选择有效的 PDF 文件")
        output = request.output_dir.expanduser().resolve()
        if request.provider not in DESKTOP_PROVIDER_LABELS:
            raise ValueError("不支持所选翻译服务")
        if request.provider != "mock" and not api_key:
            raise ValueError("所选翻译服务需要 API Key")
        if request.provider == "compatible" and (not request.base_url or not request.model):
            raise ValueError("兼容接口需要 API 地址和模型名称")
        ocr_model = (
            request.ocr_model_dir.expanduser().resolve()
            if request.ocr_model_dir is not None
            else None
        )
        if request.ocr_enabled and (ocr_model is None or not ocr_model.is_dir()):
            raise ValueError("OCR 已开启，但本地模型目录不可用")
        return DesktopJobRequest(
            source_path=source,
            output_dir=output,
            provider=request.provider,
            model=request.model,
            base_url=request.base_url,
            ocr_enabled=request.ocr_enabled,
            ocr_model_dir=ocr_model,
            target_language=request.target_language,
        )

    @staticmethod
    def _credential_environment(provider: str, api_key: str | None) -> dict[str, str]:
        if provider == "mock":
            return {}
        assert api_key is not None
        return {DESKTOP_PROVIDER_KEY_NAMES[provider]: api_key}

    def _require(self, job_id: str) -> _JobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError("Unknown desktop job") from exc

    def _persist_pdf_record(self, record: _JobRecord) -> None:
        self.library.update_pdf_task(
            record.id,
            status=record.status,
            message=record.message,
            output_dir=record.output_dir,
            output_pdf=record.output_pdf,
        )


def inspect_source(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("请选择有效的 PDF 文件")
    with pymupdf.open(source) as document:
        page_count = len(document)
    return {
        "path": str(source),
        "name": source.name,
        "size": source.stat().st_size,
        "pageCount": page_count,
    }


def _safe_error_message(exc: Exception, *, secret: str | None = None) -> str:
    message = str(exc)
    if secret:
        message = message.replace(secret, "[REDACTED]")
    if not message or "sk-" in message.lower() or "bearer " in message.lower():
        return "本地任务执行失败，请检查配置"
    return message[:300]


def _public_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if report is None:
        return None
    layout = report.get("layout", {})
    safety = report.get("layout_safety", {}).get("counts", {})
    return {
        "passed": bool(report.get("passed")),
        "overflowCount": layout.get("overflow_flow_count", 0),
        "overlapCount": safety.get("translated_overlap", 0),
        "minimumFontSize": layout.get("minimum_font_size"),
    }

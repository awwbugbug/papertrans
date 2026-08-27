from __future__ import annotations

import json
import re
import shutil
import threading
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf

LIBRARY_SCHEMA = "m7_library_v1"
PDF_TITLE_MAX_CHARACTERS = 240
TEXT_PREVIEW_MAX_CHARACTERS = 120
TEXT_PREVIEW_SCAN_CHARACTERS = 4096


class LocalTaskLibrary:
    """Small, local-only task index used by the desktop library view."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "library.json"
        self._lock = threading.RLock()

    def add_text_task(
        self,
        *,
        source_text: str,
        translation: str,
        provider: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        task_id = uuid4().hex
        timestamp = created_at or datetime.now(UTC).isoformat()
        task_dir = self.root / task_id
        task_dir.mkdir(parents=False)
        (task_dir / "source.txt").write_text(source_text, encoding="utf-8")
        (task_dir / "translation.txt").write_text(translation, encoding="utf-8")
        record = {
            "id": task_id,
            "kind": "text",
            "title": "文本翻译",
            "provider": provider,
            "status": "completed",
            "message": "文本翻译已完成",
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "characterCount": len(source_text),
        }
        with self._lock:
            records = self._read_records()
            records[task_id] = record
            self._write_records(records)
        return _summary(record, preview=_text_preview(source_text))

    def create_pdf_task(
        self,
        *,
        task_id: str,
        source_path: Path,
        output_dir: Path,
        provider: str,
        created_at: str,
    ) -> dict[str, Any]:
        record = {
            "id": task_id,
            "kind": "pdf",
            "title": _pdf_title(source_path),
            "libraryTitleResolved": True,
            "provider": provider,
            "status": "queued",
            "message": "任务已进入本地队列",
            "createdAt": created_at,
            "updatedAt": created_at,
            "sourcePath": str(source_path),
            "outputDir": str(output_dir),
            "outputPdf": None,
        }
        with self._lock:
            records = self._read_records()
            records[task_id] = record
            self._write_records(records)
        return _summary(record)

    def update_pdf_task(
        self,
        task_id: str,
        *,
        status: str,
        message: str,
        output_dir: Path | None = None,
        output_pdf: Path | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            records = self._read_records()
            record = records.get(task_id)
            if record is None or record.get("kind") != "pdf":
                raise KeyError("Unknown PDF library task")
            record["status"] = status
            record["message"] = message
            record["updatedAt"] = datetime.now(UTC).isoformat()
            if output_dir is not None:
                record["outputDir"] = str(output_dir)
            if output_pdf is not None:
                record["outputPdf"] = str(output_pdf)
            self._write_records(records)
            return _summary(record)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            records = self._read_records()
            if self._backfill_pdf_titles(records):
                self._write_records(records)
        return sorted(
            (self._summary_record(record) for record in records.values()),
            key=lambda item: str(item["updatedAt"]),
            reverse=True,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            records = self._read_records()
            if self._backfill_pdf_titles(records):
                self._write_records(records)
            record = records.get(task_id)
            if record is None:
                raise KeyError("Unknown library task")
            detail = dict(record)
        if detail.get("kind") == "text":
            task_dir = self._safe_task_dir(task_id)
            try:
                detail["sourceText"] = (task_dir / "source.txt").read_text(encoding="utf-8")
                detail["translation"] = (task_dir / "translation.txt").read_text(
                    encoding="utf-8"
                )
                detail["preview"] = _text_preview(detail["sourceText"])
            except OSError as exc:
                raise FileNotFoundError("文本任务内容不可用") from exc
        return detail

    def delete_task(self, task_id: str) -> dict[str, Any]:
        staged_dir: Path | None = None
        task_dir: Path | None = None
        with self._lock:
            records = self._read_records()
            record = records.get(task_id)
            if record is None:
                raise KeyError("Unknown library task")
            if record.get("kind") == "text":
                task_dir = self._safe_task_dir(task_id)
                if task_dir.exists():
                    staged_dir = self.root / f".deleting-{task_id}-{uuid4().hex}"
                    task_dir.replace(staged_dir)
            del records[task_id]
            try:
                self._write_records(records)
            except Exception:
                if staged_dir is not None and task_dir is not None and staged_dir.exists():
                    staged_dir.replace(task_dir)
                raise
        internal_files_removed = True
        if staged_dir is not None:
            try:
                shutil.rmtree(staged_dir)
            except OSError:
                internal_files_removed = False
        return {
            "id": task_id,
            "kind": record.get("kind"),
            "internalFilesRemoved": internal_files_removed,
        }

    def source_paths(self) -> set[Path]:
        with self._lock:
            records = self._read_records()
        return {
            Path(value).expanduser().resolve()
            for record in records.values()
            if record.get("kind") == "pdf"
            and isinstance((value := record.get("sourcePath")), str)
            and value
        }

    def open_path(self, task_id: str) -> Path:
        detail = self.get_task(task_id)
        if detail["kind"] == "text":
            return self._safe_task_dir(task_id)
        return Path(detail["outputDir"]).expanduser().resolve()

    def pdf_artifact(self, task_id: str, kind: str) -> Path:
        detail = self.get_task(task_id)
        if detail.get("kind") != "pdf":
            raise KeyError("Task is not a PDF translation")
        field = {"source": "sourcePath", "output": "outputPdf"}.get(kind)
        if field is None:
            raise KeyError("Unknown PDF artifact")
        value = detail.get(field)
        if not isinstance(value, str) or not value:
            raise FileNotFoundError("PDF artifact is unavailable")
        path = Path(value).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise FileNotFoundError("PDF artifact is unavailable")
        return path

    def pdf_output_dir(self, task_id: str) -> Path:
        detail = self.get_task(task_id)
        if detail.get("kind") != "pdf":
            raise KeyError("Task is not a PDF translation")
        value = detail.get("outputDir")
        if not isinstance(value, str) or not value:
            raise FileNotFoundError("PDF output directory is unavailable")
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError("PDF output directory is unavailable")
        return path

    def _safe_task_dir(self, task_id: str) -> Path:
        if not task_id or any(character not in "0123456789abcdef" for character in task_id):
            raise KeyError("Invalid library task")
        path = (self.root / task_id).resolve()
        if path.parent != self.root:
            raise KeyError("Invalid library task")
        return path

    def _read_records(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.is_file():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("本地任务索引损坏，请保留文件后检查") from exc
        if payload.get("schema") != LIBRARY_SCHEMA or not isinstance(payload.get("tasks"), list):
            raise RuntimeError("本地任务索引版本无效")
        return {
            record["id"]: record
            for record in payload["tasks"]
            if isinstance(record, dict) and isinstance(record.get("id"), str)
        }

    def _summary_record(self, record: dict[str, Any]) -> dict[str, Any]:
        preview = None
        if record.get("kind") == "text":
            preview = _read_text_preview(self._safe_task_dir(str(record["id"])) / "source.txt")
        return _summary(record, preview=preview)

    @staticmethod
    def _backfill_pdf_titles(records: dict[str, dict[str, Any]]) -> bool:
        changed = False
        for record in records.values():
            if record.get("kind") != "pdf" or not _uses_filename_title(record):
                continue
            source_path = record.get("sourcePath")
            if not isinstance(source_path, str) or not source_path:
                continue
            title = _pdf_title(Path(source_path))
            if title:
                record["title"] = title
            record["libraryTitleResolved"] = True
            changed = True
        return changed

    def _write_records(self, records: dict[str, dict[str, Any]]) -> None:
        payload = {"schema": LIBRARY_SCHEMA, "tasks": list(records.values())}
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.index_path)


def _summary(record: dict[str, Any], *, preview: str | None = None) -> dict[str, Any]:
    summary = {
        key: record.get(key)
        for key in (
            "id",
            "kind",
            "title",
            "provider",
            "status",
            "message",
            "createdAt",
            "updatedAt",
            "characterCount",
        )
        if key in record
    }
    if record.get("kind") == "text":
        summary["preview"] = preview or "文本内容不可用"
    return summary


def _read_text_preview(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as source:
            return _text_preview(source.read(TEXT_PREVIEW_SCAN_CHARACTERS))
    except OSError:
        return ""


def _text_preview(text: str) -> str:
    normalized = _normalize_display_text(text)
    return _truncate_display_text(normalized, TEXT_PREVIEW_MAX_CHARACTERS)


def _pdf_title(source_path: Path) -> str:
    fallback = _normalize_display_text(source_path.stem) or "未命名论文"
    try:
        with pymupdf.open(source_path) as document:
            if document.page_count == 0:
                return fallback
            visual_title = _visual_pdf_title(document[0])
            metadata_title = _metadata_pdf_title(document.metadata.get("title"), source_path)
    except (OSError, RuntimeError, ValueError):
        return _truncate_display_text(fallback, PDF_TITLE_MAX_CHARACTERS)
    return _truncate_display_text(
        visual_title or metadata_title or fallback,
        PDF_TITLE_MAX_CHARACTERS,
    )


def _visual_pdf_title(page: pymupdf.Page) -> str:
    raw = page.get_text("dict", sort=True)
    blocks = [block for block in raw.get("blocks", []) if block.get("type") == 0]
    weighted_span_sizes = [
        (float(span.get("size", 0.0)), len(str(span.get("text", "")).strip()))
        for block in blocks
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if float(span.get("size", 0.0)) > 0 and str(span.get("text", "")).strip()
    ]
    body_size = _weighted_median_size(weighted_span_sizes)
    candidates: list[tuple[float, str]] = []
    for block in blocks:
        bbox = block.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        lines = []
        sizes = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text", "")) for span in spans)
            if text.strip():
                lines.append(text)
            sizes.extend(float(span.get("size", 0.0)) for span in spans)
        title = _normalize_display_text(" ".join(lines))
        if not _valid_visual_title(title):
            continue
        x0, y0, x1, _ = (float(value) for value in bbox)
        max_size = max(sizes, default=0.0)
        if y0 > page.rect.height * 0.48:
            continue
        if body_size > 0 and max_size < max(11.0, body_size * 1.18):
            continue
        size_ratio = max_size / body_size if body_size > 0 else max_size / 10.0
        width_ratio = min(1.0, (x1 - x0) / max(1.0, page.rect.width))
        vertical_score = 1.0 - min(1.0, y0 / max(1.0, page.rect.height * 0.48))
        candidates.append((size_ratio * 4.0 + width_ratio + vertical_score, title))
    return max(candidates, default=(0.0, ""), key=lambda item: item[0])[1]


def _metadata_pdf_title(value: object, source_path: Path) -> str:
    title = _normalize_display_text(str(value or ""))
    folded = title.casefold()
    stem = _normalize_display_text(source_path.stem).casefold()
    if (
        len(title) < 5
        or folded in {stem, "untitled", "document", "microsoft word"}
        or folded.startswith("microsoft word -")
    ):
        return ""
    return title


def _valid_visual_title(title: str) -> bool:
    if not 5 <= len(title) <= 600 or not any(character.isalpha() for character in title):
        return False
    folded = title.casefold()
    return not (
        folded.startswith(("arxiv:", "doi:", "http://", "https://"))
        or "@" in title
        or re.fullmatch(r"(abstract|introduction|references)", folded) is not None
    )


def _uses_filename_title(record: dict[str, Any]) -> bool:
    if record.get("libraryTitleResolved") is True:
        return False
    title = _normalize_display_text(str(record.get("title") or ""))
    source_path = record.get("sourcePath")
    if not isinstance(source_path, str) or not source_path:
        return not title
    path = Path(source_path)
    return not title or title.casefold() in {path.name.casefold(), path.stem.casefold()}


def _normalize_display_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.replace("\x00", " "))
    return " ".join(normalized.split())


def _weighted_median_size(weighted_sizes: list[tuple[float, int]]) -> float:
    if not weighted_sizes:
        return 0.0
    threshold = sum(weight for _, weight in weighted_sizes) / 2
    cumulative = 0
    for size, weight in sorted(weighted_sizes):
        cumulative += weight
        if cumulative >= threshold:
            return size
    return weighted_sizes[-1][0]


def _truncate_display_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"

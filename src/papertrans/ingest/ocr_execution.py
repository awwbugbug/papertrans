from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pymupdf

from papertrans.domain import BoundingBox, Document, Region, RegionType, TextStyle
from papertrans.ingest.ocr_planner import OCRAction, OCRPlan, build_ocr_plan
from papertrans.ingest.pdf_reader import extract_document
from papertrans.structure import recover_document_structure


@dataclass(frozen=True, slots=True)
class OCRRuntimeConfig:
    backend: str
    model_dir: Path
    device: str = "cpu"
    dpi: int = 200


@dataclass(frozen=True, slots=True)
class RenderedOCRPage:
    page_number: int
    pixels: bytes
    pixel_width: int
    pixel_height: int
    channels: int
    page_width: float
    page_height: float


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    polygon: tuple[tuple[float, float], ...]
    confidence: float


class OCRBackend(Protocol):
    name: str

    def recognize(self, page: RenderedOCRPage) -> tuple[OCRLine, ...]: ...


@dataclass(frozen=True, slots=True)
class OCRRun:
    backend: str | None
    device: str | None
    candidate_page_count: int
    recognized_page_count: int
    recognized_line_count: int
    rejected_line_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "m6_ocr_run_v1",
            "backend": self.backend,
            "device": self.device,
            "candidate_page_count": self.candidate_page_count,
            "recognized_page_count": self.recognized_page_count,
            "recognized_line_count": self.recognized_line_count,
            "rejected_line_count": self.rejected_line_count,
        }


@dataclass(frozen=True, slots=True)
class OCRPreparationResult:
    document: Document
    plan: OCRPlan
    run: OCRRun


class PaddleOCRBackend:
    name = "paddleocr"

    def __init__(self, model_dir: str | Path, *, device: str = "cpu") -> None:
        if device not in {"cpu", "gpu"}:
            raise ValueError("OCR device must be cpu or gpu")
        self._model_dir = Path(model_dir).expanduser().resolve()
        self._device = device
        self._engine: Any | None = None

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            import paddle
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                'PaddleOCR dependencies are missing; install with pip install -e ".[ocr]"'
            ) from exc
        if self._device == "gpu" and not paddle.is_compiled_with_cuda():
            raise RuntimeError(
                "OCR device gpu requires a CUDA-enabled PaddlePaddle installation"
            )
        detection = _resolve_model_directory(
            self._model_dir, "PP-OCRv6_medium_det_infer"
        )
        recognition = _resolve_model_directory(
            self._model_dir, "PP-OCRv6_medium_rec_infer"
        )
        self._engine = PaddleOCR(
            text_detection_model_dir=str(detection),
            text_recognition_model_dir=str(recognition),
            device=self._device,
            # Paddle 3.3.1 on Windows CPU fails in the oneDNN PIR attribute bridge
            # for PP-OCRv6. The plain Paddle engine is deterministic and succeeds.
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        return self._engine

    def recognize(self, page: RenderedOCRPage) -> tuple[OCRLine, ...]:
        import numpy as np

        image = np.frombuffer(page.pixels, dtype=np.uint8).reshape(
            page.pixel_height, page.pixel_width, page.channels
        )
        lines: list[OCRLine] = []
        for result in self._load().predict(image):
            data = result.json if hasattr(result, "json") else result
            payload = data.get("res", data)
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            polygons = payload.get("rec_polys", payload.get("dt_polys", []))
            for text, score, polygon in zip(texts, scores, polygons, strict=False):
                normalized = str(text).strip()
                points = tuple((float(point[0]), float(point[1])) for point in polygon)
                if normalized and len(points) >= 4:
                    lines.append(
                        OCRLine(
                            text=normalized,
                            polygon=points,
                            confidence=max(0.0, min(1.0, float(score))),
                        )
                    )
        return tuple(lines)


def prepare_document(
    source: str | Path,
    config: OCRRuntimeConfig | None = None,
    *,
    backend: OCRBackend | None = None,
) -> OCRPreparationResult:
    source_path = Path(source).expanduser().resolve()
    document = extract_document(source_path)
    initial_plan = build_ocr_plan(document)
    candidates = tuple(
        decision.page_number
        for decision in initial_plan.pages
        if decision.action is OCRAction.RUN_OCR
    )
    if config is None:
        return OCRPreparationResult(
            document=document,
            plan=initial_plan,
            run=OCRRun(None, None, len(candidates), 0, 0, 0),
        )
    if config.backend != "paddleocr":
        raise ValueError(f"Unsupported OCR backend: {config.backend}")
    if config.dpi < 72 or config.dpi > 600:
        raise ValueError("OCR DPI must be between 72 and 600")
    resolved_backend = backend or PaddleOCRBackend(config.model_dir, device=config.device)
    page_by_number = {page.number: page for page in document.pages}
    recognized_pages = 0
    recognized_lines = 0
    rejected_lines = 0
    with pymupdf.open(source_path) as pdf:
        for page_number in candidates:
            model_page = page_by_number[page_number]
            source_page = pdf[page_number - 1]
            pixmap = source_page.get_pixmap(
                dpi=config.dpi,
                alpha=False,
                colorspace=pymupdf.csRGB,
            )
            rendered = RenderedOCRPage(
                page_number=page_number,
                pixels=bytes(pixmap.samples),
                pixel_width=pixmap.width,
                pixel_height=pixmap.height,
                channels=pixmap.n,
                page_width=model_page.width,
                page_height=model_page.height,
            )
            lines = resolved_backend.recognize(rendered)
            accepted, rejected = _fuse_ocr_lines(model_page, rendered, lines)
            recognized_lines += accepted
            rejected_lines += rejected
            if accepted:
                recognized_pages += 1
                _mark_scan_background(model_page)
    recover_document_structure(document)
    final_plan = build_ocr_plan(document, ocr_backend=resolved_backend.name)
    return OCRPreparationResult(
        document=document,
        plan=final_plan,
        run=OCRRun(
            backend=resolved_backend.name,
            device=config.device,
            candidate_page_count=len(candidates),
            recognized_page_count=recognized_pages,
            recognized_line_count=recognized_lines,
            rejected_line_count=rejected_lines,
        ),
    )


def _resolve_model_directory(root: Path, expected_name: str) -> Path:
    named = root / expected_name
    candidates = [root, named]
    if named.is_dir():
        candidates.extend(path for path in named.iterdir() if path.is_dir())
    for candidate in candidates:
        if (candidate / "inference.json").is_file() and (
            candidate / "inference.pdiparams"
        ).is_file():
            return candidate
    raise FileNotFoundError(
        f"Local OCR model {expected_name} was not found under the configured model directory"
    )


def _fuse_ocr_lines(
    page: Any,
    rendered: RenderedOCRPage,
    lines: tuple[OCRLine, ...],
) -> tuple[int, int]:
    scale_x = rendered.page_width / rendered.pixel_width
    scale_y = rendered.page_height / rendered.pixel_height
    accepted = 0
    rejected = 0
    for line in lines:
        xs = [point[0] * scale_x for point in line.polygon]
        ys = [point[1] * scale_y for point in line.polygon]
        x0 = max(0.0, min(page.width, min(xs)))
        y0 = max(0.0, min(page.height, min(ys)))
        x1 = max(0.0, min(page.width, max(xs)))
        y1 = max(0.0, min(page.height, max(ys)))
        if not line.text.strip() or x1 - x0 < 0.5 or y1 - y0 < 0.5:
            rejected += 1
            continue
        page.regions.append(
            Region(
                id=f"p{page.number}-ocr-{accepted}",
                type=RegionType.PARAGRAPH,
                bbox=BoundingBox(x0, y0, x1, y1),
                source_text=line.text,
                style=TextStyle(font_size=max(6.0, (y1 - y0) * 0.78)),
                translatable=True,
                confidence=line.confidence,
                metadata={
                    "content_source": "paddleocr",
                    "content_confidence": round(line.confidence, 4),
                    "ocr_polygon": [
                        [round(point[0] * scale_x, 3), round(point[1] * scale_y, 3)]
                        for point in line.polygon
                    ],
                },
            )
        )
        accepted += 1
    return accepted, rejected


def _mark_scan_background(page: Any) -> None:
    page_area = max(1.0, page.width * page.height)
    for region in page.regions:
        if region.metadata.get("native_block_type") != "image":
            continue
        area = max(0.0, region.bbox.width) * max(0.0, region.bbox.height)
        if area / page_area >= 0.60:
            region.metadata["ocr_background"] = True

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
    clip_bbox: BoundingBox
    source_region_id: str | None = None


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
    candidate_region_count: int = 0
    recognized_region_count: int = 0
    ignored_region_count: int = 0
    duplicate_line_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "m6_ocr_run_v2",
            "backend": self.backend,
            "device": self.device,
            "candidate_page_count": self.candidate_page_count,
            "recognized_page_count": self.recognized_page_count,
            "recognized_line_count": self.recognized_line_count,
            "rejected_line_count": self.rejected_line_count,
            "candidate_region_count": self.candidate_region_count,
            "recognized_region_count": self.recognized_region_count,
            "ignored_region_count": self.ignored_region_count,
            "duplicate_line_count": self.duplicate_line_count,
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
    candidate_regions = 0
    recognized_regions = 0
    ignored_regions = 0
    duplicate_lines = 0
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
                clip_bbox=BoundingBox(0, 0, model_page.width, model_page.height),
            )
            lines = resolved_backend.recognize(rendered)
            accepted, rejected = _fuse_ocr_lines(model_page, rendered, lines)
            recognized_lines += accepted
            rejected_lines += rejected
            if accepted:
                recognized_pages += 1
                _mark_scan_background(model_page)
        full_page_candidates = set(candidates)
        for model_page in document.pages:
            if model_page.number in full_page_candidates:
                continue
            source_page = pdf[model_page.number - 1]
            for image_region in _mixed_image_candidates(model_page):
                candidate_regions += 1
                clip = pymupdf.Rect(
                    image_region.bbox.x0,
                    image_region.bbox.y0,
                    image_region.bbox.x1,
                    image_region.bbox.y1,
                )
                pixmap = source_page.get_pixmap(
                    dpi=config.dpi,
                    alpha=False,
                    colorspace=pymupdf.csRGB,
                    clip=clip,
                )
                rendered = RenderedOCRPage(
                    page_number=model_page.number,
                    pixels=bytes(pixmap.samples),
                    pixel_width=pixmap.width,
                    pixel_height=pixmap.height,
                    channels=pixmap.n,
                    page_width=model_page.width,
                    page_height=model_page.height,
                    clip_bbox=image_region.bbox,
                    source_region_id=image_region.id,
                )
                lines = resolved_backend.recognize(rendered)
                proposed, rejected = _build_ocr_regions(model_page, rendered, lines)
                rejected_lines += rejected
                unique, duplicates = _without_native_duplicates(model_page, proposed)
                duplicate_lines += duplicates
                if not _is_text_heavy_region(unique):
                    ignored_regions += 1
                    continue
                start = sum(
                    region.metadata.get("content_source") == "paddleocr"
                    for region in model_page.regions
                )
                for index, region in enumerate(unique, start=start):
                    region.id = f"p{model_page.number}-ocr-{index}"
                    model_page.regions.append(region)
                recognized_regions += 1
                recognized_lines += len(unique)
                image_region.metadata["ocr_background"] = True
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
            candidate_region_count=candidate_regions,
            recognized_region_count=recognized_regions,
            ignored_region_count=ignored_regions,
            duplicate_line_count=duplicate_lines,
        ),
    )


def _mixed_image_candidates(page: Any) -> tuple[Region, ...]:
    page_area = max(1.0, page.width * page.height)
    return tuple(
        region
        for region in page.regions
        if region.metadata.get("native_block_type") == "image"
        and region.bbox.width / max(1.0, page.width) >= 0.25
        and region.bbox.height / max(1.0, page.height) >= 0.12
        and region.bbox.width * region.bbox.height / page_area >= 0.08
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
    regions, rejected = _build_ocr_regions(page, rendered, lines)
    start = sum(
        region.metadata.get("content_source") == "paddleocr" for region in page.regions
    )
    for index, region in enumerate(regions, start=start):
        region.id = f"p{page.number}-ocr-{index}"
        page.regions.append(region)
    return len(regions), rejected


def _build_ocr_regions(
    page: Any,
    rendered: RenderedOCRPage,
    lines: tuple[OCRLine, ...],
) -> tuple[list[Region], int]:
    scale_x = rendered.clip_bbox.width / rendered.pixel_width
    scale_y = rendered.clip_bbox.height / rendered.pixel_height
    regions: list[Region] = []
    rejected = 0
    for line in lines:
        xs = [rendered.clip_bbox.x0 + point[0] * scale_x for point in line.polygon]
        ys = [rendered.clip_bbox.y0 + point[1] * scale_y for point in line.polygon]
        x0 = max(0.0, min(page.width, min(xs)))
        y0 = max(0.0, min(page.height, min(ys)))
        x1 = max(0.0, min(page.width, max(xs)))
        y1 = max(0.0, min(page.height, max(ys)))
        if not line.text.strip() or x1 - x0 < 0.5 or y1 - y0 < 0.5:
            rejected += 1
            continue
        regions.append(
            Region(
                id=f"p{page.number}-ocr-proposed-{len(regions)}",
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
                        [
                            round(rendered.clip_bbox.x0 + point[0] * scale_x, 3),
                            round(rendered.clip_bbox.y0 + point[1] * scale_y, 3),
                        ]
                        for point in line.polygon
                    ],
                    "ocr_source_region_id": rendered.source_region_id,
                },
            )
        )
    return regions, rejected


def _without_native_duplicates(
    page: Any, proposed: list[Region]
) -> tuple[list[Region], int]:
    native = [
        region
        for region in page.regions
        if region.source_text and region.metadata.get("content_source") == "native_pdf"
    ]
    unique: list[Region] = []
    duplicate_count = 0
    for region in proposed:
        area = max(1.0, region.bbox.width * region.bbox.height)
        if any(_intersection_area(region.bbox, item.bbox) / area >= 0.5 for item in native):
            duplicate_count += 1
        else:
            unique.append(region)
    return unique, duplicate_count


def _intersection_area(first: BoundingBox, second: BoundingBox) -> float:
    width = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0))
    height = max(0.0, min(first.y1, second.y1) - max(first.y0, second.y0))
    return width * height


def _is_text_heavy_region(regions: list[Region]) -> bool:
    if len(regions) < 3:
        return False
    character_count = sum(
        not character.isspace()
        for region in regions
        for character in region.source_text or ""
    )
    mean_confidence = sum(region.confidence for region in regions) / len(regions)
    return character_count >= 80 and mean_confidence >= 0.80


def _mark_scan_background(page: Any) -> None:
    page_area = max(1.0, page.width * page.height)
    for region in page.regions:
        if region.metadata.get("native_block_type") != "image":
            continue
        area = max(0.0, region.bbox.width) * max(0.0, region.bbox.height)
        if area / page_area >= 0.60:
            region.metadata["ocr_background"] = True

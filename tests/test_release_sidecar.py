"""Opt-in regression gate against the actual frozen Windows sidecar, not Python source."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pymupdf
import pytest


@pytest.mark.skipif(
    not os.environ.get("PAPERTRANS_RELEASE_SIDECAR"),
    reason="requires a freshly built Windows sidecar and local OCR models",
)
def test_frozen_sidecar_recognizes_and_translates_a_scan(tmp_path: Path) -> None:
    """Missing PaddleX pipeline data must fail the release, even if /api/system works."""
    sidecar = Path(os.environ["PAPERTRANS_RELEASE_SIDECAR"]).resolve()
    models = Path(os.environ["PAPERTRANS_RELEASE_OCR_MODELS"]).resolve()
    assert sidecar.is_file()
    assert models.is_dir()
    source = tmp_path / "synthetic-scan.pdf"
    output = tmp_path / "output"
    with pymupdf.open() as text_pdf:
        page = text_pdf.new_page(width=400, height=600)
        remaining = page.insert_textbox(
            pymupdf.Rect(40, 80, 360, 350),
            "This academic paper describes a reliable local document translation method. "
            "The experiment compares text recognition and layout recovery. "
            "Our system preserves paragraph boundaries and checks the final output. "
            "This example uses synthetic text and local model files only.",
            fontsize=12,
        )
        assert remaining >= 0
        raster = page.get_pixmap(dpi=200, alpha=False).tobytes("png")
    with pymupdf.open() as scan_pdf:
        page = scan_pdf.new_page(width=400, height=600)
        page.insert_image(page.rect, stream=raster)
        scan_pdf.save(source)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = secrets.token_urlsafe(32)
    environment = {
        **os.environ,
        "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
        "HF_HUB_OFFLINE": "1",
    }
    process = subprocess.Popen(
        [
            str(sidecar), "--port", str(port), "--token", token,
            "--data-root", str(tmp_path / "data"), "--ocr-model-dir", str(models),
        ],
        cwd=tmp_path,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False
        ) as client:
            deadline = time.monotonic() + 90
            while True:
                try:
                    response = client.get("/api/system")
                    break
                except httpx.TransportError:
                    assert process.poll() is None, "frozen sidecar exited before startup"
                    assert time.monotonic() < deadline, "frozen sidecar startup timed out"
                    time.sleep(0.5)
            assert response.status_code == 401
            client.headers["X-PaperTrans-Token"] = token
            response = client.get("/api/system")
            response.raise_for_status()
            assert response.json()["ocr"]["ready"] is True
            response = client.post(
                "/api/jobs",
                json={
                    "sourcePath": str(source), "outputDir": str(output),
                    "provider": "mock", "ocrEnabled": True, "ocrModelDir": str(models),
                },
            )
            response.raise_for_status()
            job_id = response.json()["id"]
            deadline = time.monotonic() + 180
            while True:
                # Cold model initialization can briefly delay API worker responses.
                # Retry only this read, bounded by the same overall job deadline.
                assert time.monotonic() < deadline, "frozen OCR job timed out"
                try:
                    response = client.get(
                        f"/api/jobs/{job_id}",
                        timeout=min(30, max(0.1, deadline - time.monotonic())),
                    )
                except httpx.TransportError:
                    assert process.poll() is None, (
                        f"frozen sidecar exited during OCR ({process.returncode})"
                    )
                    time.sleep(0.5)
                    continue
                response.raise_for_status()
                result = response.json()
                if result["status"] not in {"queued", "running"}:
                    break
                assert time.monotonic() < deadline, "frozen OCR job timed out"
                time.sleep(0.5)
            assert result["status"] == "completed", result["message"]
            assert result["outputAvailable"] is True
            assert result["report"]["passed"] is True
            reports = list(output.rglob("ocr-run.json"))
            assert len(reports) == 1
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            assert report["backend"] == "paddleocr"
            assert report["recognized_page_count"] == 1
            assert report["recognized_line_count"] >= 3
            response = client.get(f"/api/jobs/{job_id}/output")
            response.raise_for_status()
            with pymupdf.open(stream=response.content, filetype="pdf") as translated:
                assert len(translated) == 1
                assert translated[0].rect == pymupdf.Rect(0, 0, 400, 600)
    finally:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        process.wait(timeout=15)

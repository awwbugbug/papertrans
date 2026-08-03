from pathlib import Path
from types import SimpleNamespace

import pymupdf

from papertrans.desktop.jobs import DesktopJobManager, DesktopJobRequest


class FakeProvider:
    name = "mock"


def _pdf(path: Path) -> None:
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()


def test_desktop_job_runs_without_persisting_credentials(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    output_pdf = tmp_path / "out" / "paper-mock-translation" / "output.pdf"
    _pdf(source)

    def runner(source_path, output_dir, provider, **kwargs):  # type: ignore[no-untyped-def]
        resolved = Path(output_dir)
        resolved.mkdir(parents=True)
        output_pdf.write_bytes(b"%PDF-fixture")
        return SimpleNamespace(
            output_dir=resolved,
            output_pdf=output_pdf,
            report={
                "passed": True,
                "layout": {"overflow_flow_count": 0, "minimum_font_size": 8.0},
                "layout_safety": {"counts": {"translated_overlap": 0}},
            },
        )

    manager = DesktopJobManager(
        tmp_path / "jobs",
        provider_factory=lambda *args, **kwargs: FakeProvider(),
        runner=runner,
    )
    started = manager.start(
        DesktopJobRequest(source, tmp_path / "out", provider="mock"),
        api_key=None,
    )
    completed = manager.wait(started["id"])

    assert completed["status"] == "completed"
    assert completed["outputAvailable"] is True
    assert "api" not in str(completed).lower()
    assert completed["report"]["overflowCount"] == 0
    manager.shutdown()


def test_desktop_job_requires_external_provider_key_without_storing_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    _pdf(source)
    manager = DesktopJobManager(tmp_path / "jobs")

    try:
        manager.start(
            DesktopJobRequest(source, tmp_path / "out", provider="deepseek")
        )
    except ValueError as exc:
        assert "API Key" in str(exc)
    else:
        raise AssertionError("missing API key should fail")
    finally:
        manager.shutdown()


def test_desktop_job_redacts_session_credential_from_provider_errors(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    _pdf(source)
    secret = "credential-without-provider-prefix"

    def failing_provider(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValueError(f"provider rejected {secret}")

    manager = DesktopJobManager(tmp_path / "jobs", provider_factory=failing_provider)
    started = manager.start(
        DesktopJobRequest(source, tmp_path / "out", provider="deepseek"),
        api_key=secret,
    )
    failed = manager.wait(started["id"])

    assert failed["status"] == "failed"
    assert secret not in failed["message"]
    assert "[REDACTED]" in failed["message"]
    manager.shutdown()

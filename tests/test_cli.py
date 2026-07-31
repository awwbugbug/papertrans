import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest

from papertrans.cli import build_parser, main


def test_translate_defaults_to_mock_without_api_key_argument() -> None:
    parser = build_parser()
    args = parser.parse_args(["translate", "paper.pdf"])
    assert args.provider == "mock"
    assert args.model is None
    assert args.base_url is None
    assert args.api_key_env is None
    assert args.glossary is None
    option_strings = {
        option
        for action in parser._subparsers._group_actions[0].choices[
            "translate"
        ]._actions
        for option in action.option_strings
    }
    assert "--api-key" not in option_strings


def test_translate_accepts_named_and_compatible_configuration() -> None:
    parser = build_parser()
    deepseek = parser.parse_args(
        [
            "translate",
            "paper.pdf",
            "--provider",
            "deepseek",
            "--model",
            "deepseek-v4-flash",
            "--timeout",
            "45",
            "--max-output-tokens",
            "1200",
        ]
    )
    assert deepseek.provider == "deepseek"
    assert deepseek.timeout == 45
    assert deepseek.max_output_tokens == 1200
    compatible = parser.parse_args(
        [
            "translate",
            "paper.pdf",
            "--provider",
            "compatible",
            "--base-url",
            "https://relay.test/v1",
            "--model",
            "cheap-model",
            "--api-key-env",
            "RELAY_API_KEY",
        ]
    )
    assert compatible.base_url == "https://relay.test/v1"
    assert compatible.api_key_env == "RELAY_API_KEY"


def test_all_cli_parsers_disable_long_option_abbreviation() -> None:
    parser = build_parser()
    command_parsers = parser._subparsers._group_actions[0].choices.values()

    assert parser.allow_abbrev is False
    assert all(
        command_parser.allow_abbrev is False for command_parser in command_parsers
    )


def test_main_rejects_api_key_option_without_echoing_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = "PaperTransKey1234567890"

    with pytest.raises(SystemExit):
        main(
            [
                "translate",
                "paper.pdf",
                "--provider",
                "compatible",
                "--base-url",
                "https://relay.test/v1",
                "--model",
                "cheap-model",
                "--api-key",
                sentinel,
            ]
        )

    captured = capsys.readouterr()
    assert "API keys must be supplied through environment variables" in captured.err
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_main_reports_missing_selected_credential_environment_generically(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = "PAPERTRANS_MISSING_KEY_987654321"

    with pytest.raises(SystemExit):
        main(
            [
                "translate",
                "paper.pdf",
                "--provider",
                "compatible",
                "--base-url",
                "https://relay.test/v1",
                "--model",
                "cheap-model",
                "--api-key-env",
                sentinel,
            ]
        )

    captured = capsys.readouterr()
    assert "Required API credential environment variable is not set" in captured.err
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_parser_rejects_unknown_provider() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["translate", str(Path("paper.pdf")), "--provider", "unknown"]
        )


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    [
        (
            ["--provider", "mock", "--model", "ignored-model"],
            "--model is not valid with provider mock",
        ),
        (
            ["--provider", "deepseek", "--length-factor", "1.1"],
            "--length-factor is only valid with provider mock",
        ),
        (
            ["--provider", "kimi", "--length-factor", "1.1"],
            "--length-factor is only valid with provider mock",
        ),
        (
            ["--provider", "compatible", "--length-factor", "1.1"],
            "--length-factor is only valid with provider mock",
        ),
        (
            [
                "--provider",
                "deepseek",
                "--base-url",
                "https://relay.test/v1",
            ],
            "--base-url and --api-key-env are only valid with provider compatible",
        ),
        (
            ["--provider", "kimi", "--api-key-env", "KIMI_OVERRIDE"],
            "--base-url and --api-key-env are only valid with provider compatible",
        ),
    ],
)
def test_main_rejects_provider_incompatible_options(
    arguments: list[str],
    expected_error: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(["translate", "paper.pdf", *arguments])

    captured = capsys.readouterr()
    assert expected_error in captured.err


def test_main_rejects_secret_shaped_api_key_environment_name_without_echo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = "sk-sensitive-value-123456"

    with pytest.raises(SystemExit):
        main(
            [
                "translate",
                "paper.pdf",
                "--provider",
                "compatible",
                "--base-url",
                "https://relay.test/v1",
                "--model",
                "cheap-model",
                "--api-key-env",
                sentinel,
            ]
        )

    captured = capsys.readouterr()
    assert "--api-key-env must be a valid environment variable name" in captured.err
    assert sentinel not in captured.out
    assert sentinel not in captured.err


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    [
        (["--timeout", "nan"], "--timeout must be finite and greater than 0"),
        (["--timeout", "inf"], "--timeout must be finite and greater than 0"),
        (["--timeout", "0"], "--timeout must be finite and greater than 0"),
        (["--timeout", "-1"], "--timeout must be finite and greater than 0"),
        (
            ["--length-factor", "nan"],
            "--length-factor must be finite and greater than 0",
        ),
        (
            ["--length-factor", "inf"],
            "--length-factor must be finite and greater than 0",
        ),
        (
            ["--length-factor", "0"],
            "--length-factor must be finite and greater than 0",
        ),
        (
            ["--length-factor", "-0.1"],
            "--length-factor must be finite and greater than 0",
        ),
        (
            ["--requests-per-second", "nan"],
            "--requests-per-second must be finite and greater than or equal to 0",
        ),
        (
            ["--requests-per-second", "inf"],
            "--requests-per-second must be finite and greater than or equal to 0",
        ),
        (
            ["--requests-per-second", "-1"],
            "--requests-per-second must be finite and greater than or equal to 0",
        ),
        (
            ["--max-output-tokens", "0"],
            "--max-output-tokens must be greater than 0",
        ),
        (
            ["--max-output-tokens", "-1"],
            "--max-output-tokens must be greater than 0",
        ),
        (["--max-attempts", "0"], "--max-attempts must be greater than 0"),
    ],
)
def test_main_rejects_invalid_numeric_options_before_provider_creation(
    arguments: list[str],
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def fake_create(*args: object, **kwargs: object) -> object:
        calls.append("provider")
        return object()

    def fake_run(*args: object, **kwargs: object) -> object:
        calls.append("job")
        return SimpleNamespace(
            output_dir=Path("output"),
            output_pdf=Path("output/output.pdf"),
            protected_segments_json=Path("output/protected-segments.json"),
            provider_run_json=Path("output/provider-run.json"),
            translations_json=Path("output/translations.json"),
            layout_json=Path("output/layout.json"),
            report_json=Path("output/translation-report.json"),
            report={"passed": True},
        )

    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        fake_create,
    )
    monkeypatch.setattr(
        "papertrans.cli.run_translation_job",
        fake_run,
    )

    with pytest.raises(SystemExit):
        main(["translate", "paper.pdf", *arguments])

    assert expected_error in capsys.readouterr().err
    assert calls == []


def test_zero_requests_per_second_remains_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    output = tmp_path / "output"

    def fake_run(*args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(
            output_dir=output,
            output_pdf=output / "output.pdf",
            ocr_plan_json=output / "ocr-plan.json",
            protected_segments_json=output / "protected-segments.json",
            provider_run_json=output / "provider-run.json",
            translations_json=output / "translations.json",
            layout_json=output / "layout.json",
            report_json=output / "translation-report.json",
            report={"passed": True},
        )

    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr("papertrans.cli.run_translation_job", fake_run)

    main(
        [
            "translate",
            "paper.pdf",
            "--requests-per-second",
            "0",
            "--output-dir",
            str(output),
        ]
    )

    assert captured["requests_per_second"] == 0.0
    assert "Quality gate:       PASS" in capsys.readouterr().out


def test_main_reports_review_without_claiming_output_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "output"

    def fake_run(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(
            output_dir=output,
            output_pdf=output / "output.pdf",
            ocr_plan_json=output / "ocr-plan.json",
            protected_segments_json=output / "protected-segments.json",
            provider_run_json=output / "provider-run.json",
            translations_json=output / "translations.json",
            layout_json=output / "layout.json",
            report_json=output / "translation-report.json",
            report={
                "passed": False,
                "output_replaced": False,
                "review_reasons": ["overflow"],
            },
        )

    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr("papertrans.cli.run_translation_job", fake_run)

    main(["translate", "paper.pdf", "--output-dir", str(output)])

    stdout = capsys.readouterr().out
    assert "Translation needs review" in stdout
    assert "Output PDF:         not created or replaced" in stdout
    assert "Review reasons:     overflow" in stdout
    assert "Quality gate:       REVIEW" in stdout


def test_main_loads_glossary_before_provider_and_passes_terms_to_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(
        '{"region proposal": "候选区域"}',
        encoding="utf-8",
    )
    output = tmp_path / "output"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: object(),
    )

    def fake_run(*args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(
            output_dir=output,
            output_pdf=output / "output.pdf",
            ocr_plan_json=output / "ocr-plan.json",
            protected_segments_json=output / "protected-segments.json",
            provider_run_json=output / "provider-run.json",
            translations_json=output / "translations.json",
            layout_json=output / "layout.json",
            report_json=output / "translation-report.json",
            report={"passed": True},
        )

    monkeypatch.setattr("papertrans.cli.run_translation_job", fake_run)

    main(
        [
            "translate",
            "paper.pdf",
            "--glossary",
            str(glossary_path),
            "--output-dir",
            str(output),
        ]
    )

    assert captured["glossary"] == {"region proposal": "候选区域"}


def test_main_rejects_invalid_glossary_before_provider_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: calls.append("provider"),
    )

    with pytest.raises(SystemExit):
        main(["translate", "paper.pdf", "--glossary", str(invalid)])

    assert "Invalid glossary file" in capsys.readouterr().err
    assert calls == []


def test_main_dispatches_selected_provider_to_generic_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    class ProviderMarker:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1

    provider_marker = ProviderMarker()
    output = tmp_path / "output"

    def fake_create(name: str, **kwargs: object) -> object:
        captured["name"] = name
        captured["settings"] = kwargs
        return provider_marker

    def fake_run(
        source: Path, output_dir: Path, provider: object, **kwargs: object
    ) -> object:
        captured["provider"] = provider
        captured["output_dir"] = output_dir
        return SimpleNamespace(
            output_dir=output,
            output_pdf=output / "output.pdf",
            ocr_plan_json=output / "ocr-plan.json",
            protected_segments_json=output / "protected-segments.json",
            provider_run_json=output / "provider-run.json",
            translations_json=output / "translations.json",
            layout_json=output / "layout.json",
            report_json=output / "translation-report.json",
            report={"passed": True},
        )

    monkeypatch.setattr("papertrans.cli.create_translation_provider", fake_create)
    monkeypatch.setattr("papertrans.cli.run_translation_job", fake_run)
    main(
        [
            "translate",
            str(tmp_path / "paper.pdf"),
            "--provider",
            "kimi",
            "--output-dir",
            str(output),
        ]
    )
    assert captured["name"] == "kimi"
    assert captured["provider"] is provider_marker
    assert captured["output_dir"] == output
    assert provider_marker.close_count == 1
    assert "Quality gate:       PASS" in capsys.readouterr().out


def test_main_closes_provider_when_translation_job_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class CloseableProvider:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1

    provider = CloseableProvider()
    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: provider,
    )

    def fail_job(*args: object, **kwargs: object) -> object:
        raise RuntimeError("sanitized_job_failure")

    monkeypatch.setattr("papertrans.cli.run_translation_job", fail_job)

    with pytest.raises(SystemExit):
        main(["translate", "paper.pdf"])

    assert provider.close_count == 1
    assert "sanitized_job_failure" in capsys.readouterr().err


def test_raising_close_cannot_mask_parser_error_or_leak_cleanup_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cleanup_sentinel = "cleanup_failure_sensitive_text"

    class RaisingCloseProvider:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1
            raise RuntimeError(cleanup_sentinel)

    provider = RaisingCloseProvider()
    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: provider,
    )

    def fail_job(*args: object, **kwargs: object) -> object:
        raise RuntimeError("sanitized_job_failure")

    monkeypatch.setattr("papertrans.cli.run_translation_job", fail_job)

    with pytest.raises(BaseException) as exc_info:
        main(["translate", "paper.pdf"])

    captured = capsys.readouterr()
    formatted = "".join(
        traceback.format_exception(
            exc_info.type,
            exc_info.value,
            exc_info.value.__traceback__,
        )
    )
    assert isinstance(exc_info.value, SystemExit)
    assert provider.close_count == 1
    assert "sanitized_job_failure" in captured.err
    assert cleanup_sentinel not in captured.out
    assert cleanup_sentinel not in captured.err
    assert cleanup_sentinel not in formatted


def test_raising_close_cannot_mask_unexpected_primary_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_sentinel = "cleanup_failure_sensitive_text"

    class RaisingCloseProvider:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1
            raise RuntimeError(cleanup_sentinel)

    provider = RaisingCloseProvider()
    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: provider,
    )

    def fail_job(*args: object, **kwargs: object) -> object:
        raise LookupError("primary_unexpected_failure")

    monkeypatch.setattr("papertrans.cli.run_translation_job", fail_job)

    with pytest.raises(BaseException) as exc_info:
        main(["translate", "paper.pdf"])

    formatted = "".join(
        traceback.format_exception(
            exc_info.type,
            exc_info.value,
            exc_info.value.__traceback__,
        )
    )
    assert isinstance(exc_info.value, LookupError)
    assert str(exc_info.value) == "primary_unexpected_failure"
    assert provider.close_count == 1
    assert cleanup_sentinel not in formatted


def test_cleanup_only_failure_is_sanitized_and_not_ignored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cleanup_sentinel = "cleanup_failure_sensitive_text"
    output = tmp_path / "output"

    class RaisingCloseProvider:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1
            raise RuntimeError(cleanup_sentinel)

    provider = RaisingCloseProvider()
    monkeypatch.setattr(
        "papertrans.cli.create_translation_provider",
        lambda *args, **kwargs: provider,
    )
    monkeypatch.setattr(
        "papertrans.cli.run_translation_job",
        lambda *args, **kwargs: SimpleNamespace(
            output_dir=output,
            output_pdf=output / "output.pdf",
            ocr_plan_json=output / "ocr-plan.json",
            protected_segments_json=output / "protected-segments.json",
            provider_run_json=output / "provider-run.json",
            translations_json=output / "translations.json",
            layout_json=output / "layout.json",
            report_json=output / "translation-report.json",
            report={"passed": True},
        ),
    )

    with pytest.raises(BaseException) as exc_info:
        main(["translate", "paper.pdf", "--output-dir", str(output)])

    captured = capsys.readouterr()
    formatted = "".join(
        traceback.format_exception(
            exc_info.type,
            exc_info.value,
            exc_info.value.__traceback__,
        )
    )
    assert isinstance(exc_info.value, SystemExit)
    assert provider.close_count == 1
    assert "Translation provider cleanup failed" in captured.err
    assert cleanup_sentinel not in captured.out
    assert cleanup_sentinel not in captured.err
    assert cleanup_sentinel not in formatted

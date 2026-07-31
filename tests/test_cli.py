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


def test_parser_rejects_unknown_provider() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["translate", str(Path("paper.pdf")), "--provider", "unknown"]
        )


def test_main_dispatches_selected_provider_to_generic_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    provider_marker = object()
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
    assert "Quality gate:       PASS" in capsys.readouterr().out

from __future__ import annotations

import argparse
import math
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from papertrans import __version__
from papertrans.ingest import OCRRuntimeConfig
from papertrans.inspect import inspect_pdf
from papertrans.roundtrip import run_roundtrip
from papertrans.translation import (
    PROVIDER_NAMES,
    CloseableTranslationProvider,
    TranslationProvider,
    create_translation_provider,
    load_glossary,
)
from papertrans.translation_job import run_translation_job

_ENVIRONMENT_VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _add_ocr_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ocr-backend",
        choices=("paddleocr",),
        help="Opt in to selective local OCR for scan-like pages",
    )
    parser.add_argument(
        "--ocr-model-dir",
        type=Path,
        help="Directory containing the extracted PP-OCRv6 detection and recognition models",
    )
    parser.add_argument(
        "--ocr-device",
        choices=("cpu", "gpu"),
        default="cpu",
        help="Local OCR inference device (default: cpu)",
    )
    parser.add_argument(
        "--ocr-dpi",
        type=int,
        default=200,
        help="Rasterization DPI for selected OCR pages (default: 200)",
    )


def _ocr_runtime_config(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> OCRRuntimeConfig | None:
    if args.ocr_backend is None:
        if args.ocr_model_dir is not None:
            parser.error("--ocr-model-dir requires --ocr-backend paddleocr")
        return None
    if args.ocr_model_dir is None:
        parser.error("--ocr-backend paddleocr requires --ocr-model-dir")
    if not 72 <= args.ocr_dpi <= 600:
        parser.error("--ocr-dpi must be between 72 and 600")
    return OCRRuntimeConfig(
        backend=args.ocr_backend,
        model_dir=args.ocr_model_dir,
        device=args.ocr_device,
        dpi=args.ocr_dpi,
    )


class _SafeArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def parse_known_args(
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> tuple[argparse.Namespace, list[str]]:
        arguments = sys.argv[1:] if args is None else args
        if any(
            argument == "--api-key" or argument.startswith("--api-key=")
            for argument in arguments
        ):
            self.error("API keys must be supplied through environment variables")
        return super().parse_known_args(args, namespace)


def _default_output(source: Path, operation: str) -> Path:
    return source.parent / ".papertrans" / f"{source.stem}-{operation}"


def _validate_translate_args(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if args.api_key_env is not None and not _ENVIRONMENT_VARIABLE_NAME.fullmatch(
        args.api_key_env
    ):
        parser.error("--api-key-env must be a valid environment variable name")
    if args.provider == "mock" and args.model is not None:
        parser.error("--model is not valid with provider mock")
    if args.provider != "mock" and args.length_factor is not None:
        parser.error("--length-factor is only valid with provider mock")
    if args.provider != "compatible" and (
        args.base_url is not None or args.api_key_env is not None
    ):
        parser.error(
            "--base-url and --api-key-env are only valid with provider compatible"
        )
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and greater than 0")
    if args.length_factor is not None and (
        not math.isfinite(args.length_factor) or args.length_factor <= 0
    ):
        parser.error("--length-factor must be finite and greater than 0")
    if (
        not math.isfinite(args.requests_per_second)
        or args.requests_per_second < 0
    ):
        parser.error(
            "--requests-per-second must be finite and greater than or equal to 0"
        )
    if args.max_output_tokens <= 0:
        parser.error("--max-output-tokens must be greater than 0")
    if args.max_attempts <= 0:
        parser.error("--max-attempts must be greater than 0")


def build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="papertrans",
        description="Layout-aware academic PDF translation toolkit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Extract and visualize the baseline structure of a PDF",
    )
    inspect_parser.add_argument("input", type=Path, help="Source PDF")
    inspect_parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Inspection artifact directory",
    )
    _add_ocr_arguments(inspect_parser)
    roundtrip_parser = subparsers.add_parser(
        "roundtrip",
        help="Remove and redraw translatable source text without translation",
    )
    roundtrip_parser.add_argument("input", type=Path, help="Source PDF")
    roundtrip_parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Roundtrip artifact directory",
    )
    translate_parser = subparsers.add_parser(
        "translate",
        help="Translate document text flows with an available provider",
    )
    translate_parser.add_argument("input", type=Path, help="Source PDF")
    translate_parser.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        default="mock",
        help="Translation provider",
    )
    translate_parser.add_argument("--model", help="Provider model override")
    translate_parser.add_argument(
        "--base-url",
        help="OpenAI-compatible API base URL; only valid with compatible",
    )
    translate_parser.add_argument(
        "--api-key-env",
        help="Environment variable containing the compatible API key",
    )
    translate_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Provider request timeout in seconds",
    )
    translate_parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=2048,
        help="Maximum provider output tokens per request",
    )
    translate_parser.add_argument(
        "--length-factor",
        type=float,
        help="Mock translation length multiplier",
    )
    translate_parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Translation artifact directory",
    )
    translate_parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Persistent provider cache directory",
    )
    translate_parser.add_argument(
        "--glossary",
        type=Path,
        help="Optional UTF-8 JSON object mapping source terms to Chinese terms",
    )
    translate_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum provider attempts per segment",
    )
    translate_parser.add_argument(
        "--requests-per-second",
        type=float,
        default=0.0,
        help="Provider request rate; 0 disables rate limiting",
    )
    _add_ocr_arguments(translate_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        source = args.input.expanduser().resolve()
        output = args.output_dir or _default_output(source, "inspect")
        try:
            result = inspect_pdf(source, output, ocr_config=_ocr_runtime_config(parser, args))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        print(f"Inspection complete: {result.output_dir}")
        print(f"Document model:     {result.document_json}")
        print(f"Text flows:         {result.text_flows_json}")
        print(f"OCR plan:           {result.ocr_plan_json}")
        if getattr(result, "ocr_run_json", None) is not None:
            print(f"OCR run:            {result.ocr_run_json}")
        print(f"Inspection report:  {result.report_markdown}")
    elif args.command == "roundtrip":
        source = args.input.expanduser().resolve()
        output = args.output_dir or _default_output(source, "roundtrip")
        try:
            result = run_roundtrip(source, output)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        status = "PASS" if result.report["passed"] else "REVIEW"
        print(f"Roundtrip complete: {result.output_dir}")
        print(f"Output PDF:         {result.output_pdf}")
        print(f"Quality report:     {result.report_json}")
        print(f"Quality gate:       {status}")
    elif args.command == "translate":
        _validate_translate_args(parser, args)
        ocr_config = _ocr_runtime_config(parser, args)
        source = args.input.expanduser().resolve()
        output = args.output_dir or _default_output(
            source, f"{args.provider}-translation"
        )
        provider: TranslationProvider | None = None
        result = None
        primary_error: BaseException | None = None
        try:
            glossary = load_glossary(args.glossary) if args.glossary is not None else {}
            provider = create_translation_provider(
                args.provider,
                model=args.model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                length_factor=(
                    1.0 if args.length_factor is None else args.length_factor
                ),
                timeout_seconds=args.timeout,
                max_output_tokens=args.max_output_tokens,
            )
            result = run_translation_job(
                source,
                output,
                provider,
                cache_dir=args.cache_dir,
                max_attempts=args.max_attempts,
                requests_per_second=args.requests_per_second,
                glossary=glossary,
                ocr_config=ocr_config,
            )
        except BaseException as exc:
            primary_error = exc

        cleanup_failed = False
        if isinstance(provider, CloseableTranslationProvider):
            try:
                provider.close()
            except BaseException:
                cleanup_failed = True

        if primary_error is not None:
            if isinstance(primary_error, (FileNotFoundError, ValueError, RuntimeError)):
                parser.error(str(primary_error))
            raise primary_error.with_traceback(primary_error.__traceback__) from None
        if cleanup_failed:
            parser.error("Translation provider cleanup failed")
        assert result is not None
        status = "PASS" if result.report["passed"] else "REVIEW"
        outcome = "Translation complete" if result.report["passed"] else "Translation needs review"
        print(f"{outcome}: {result.output_dir}")
        print(f"Provider:             {args.provider}")
        if result.report["passed"]:
            print(f"Output PDF:         {result.output_pdf}")
        else:
            print("Output PDF:         not created or replaced")
            reasons = ", ".join(result.report.get("review_reasons", []))
            if reasons:
                print(f"Review reasons:     {reasons}")
        print(f"Protected segments: {result.protected_segments_json}")
        print(f"OCR plan:           {result.ocr_plan_json}")
        if getattr(result, "ocr_run_json", None) is not None:
            print(f"OCR run:            {result.ocr_run_json}")
        print(f"Provider run:       {result.provider_run_json}")
        print(f"Translations:       {result.translations_json}")
        print(f"Layout:             {result.layout_json}")
        print(f"Quality report:     {result.report_json}")
        print(f"Quality gate:       {status}")

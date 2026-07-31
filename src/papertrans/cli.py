from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from papertrans import __version__
from papertrans.inspect import inspect_pdf
from papertrans.roundtrip import run_roundtrip
from papertrans.translation import PROVIDER_NAMES, create_translation_provider
from papertrans.translation_job import run_translation_job


def _default_output(source: Path, operation: str) -> Path:
    return source.parent / ".papertrans" / f"{source.stem}-{operation}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
        default=1.0,
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
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        source = args.input.expanduser().resolve()
        output = args.output_dir or _default_output(source, "inspect")
        try:
            result = inspect_pdf(source, output)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        print(f"Inspection complete: {result.output_dir}")
        print(f"Document model:     {result.document_json}")
        print(f"Text flows:         {result.text_flows_json}")
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
        source = args.input.expanduser().resolve()
        output = args.output_dir or _default_output(
            source, f"{args.provider}-translation"
        )
        try:
            provider = create_translation_provider(
                args.provider,
                model=args.model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                length_factor=args.length_factor,
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
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        status = "PASS" if result.report["passed"] else "REVIEW"
        print(f"Translation complete: {result.output_dir}")
        print(f"Provider:             {args.provider}")
        print(f"Output PDF:         {result.output_pdf}")
        print(f"Protected segments: {result.protected_segments_json}")
        print(f"Provider run:       {result.provider_run_json}")
        print(f"Translations:       {result.translations_json}")
        print(f"Layout:             {result.layout_json}")
        print(f"Quality report:     {result.report_json}")
        print(f"Quality gate:       {status}")

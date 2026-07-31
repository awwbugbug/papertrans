from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from papertrans import __version__
from papertrans.inspect import inspect_pdf
from papertrans.mock_translation import run_mock_translation
from papertrans.roundtrip import run_roundtrip


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
        choices=("mock",),
        default="mock",
        help="Translation provider; M4.2 currently supports reliable protected mock translation",
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
        output = args.output_dir or _default_output(source, "mock-translation")
        try:
            result = run_mock_translation(
                source,
                output,
                length_factor=args.length_factor,
                cache_dir=args.cache_dir,
                max_attempts=args.max_attempts,
                requests_per_second=args.requests_per_second,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        status = "PASS" if result.report["passed"] else "REVIEW"
        print(f"Mock translation:   {result.output_dir}")
        print(f"Output PDF:         {result.output_pdf}")
        print(f"Protected segments: {result.protected_segments_json}")
        print(f"Provider run:       {result.provider_run_json}")
        print(f"Translations:       {result.translations_json}")
        print(f"Layout:             {result.layout_json}")
        print(f"Quality report:     {result.report_json}")
        print(f"Quality gate:       {status}")

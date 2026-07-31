from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True, slots=True)
class ResolvedCJKFont:
    path: Path
    fontname: str
    bold: bool
    metrics: pymupdf.Font


class CJKFontResolver:
    """Resolve a local CJK font without downloading or bundling font files."""

    def __init__(self) -> None:
        normal_override = os.environ.get("PAPERTRANS_CJK_FONT")
        bold_override = os.environ.get("PAPERTRANS_CJK_BOLD_FONT")
        self.normal_path = self._first_existing(
            [
                normal_override,
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
            ]
        )
        self.bold_path = self._first_existing(
            [
                bold_override,
                "C:/Windows/Fonts/msyhbd.ttc",
                str(self.normal_path) if self.normal_path else None,
            ]
        )
        if self.normal_path is None:
            raise RuntimeError(
                "No local CJK font found. Set PAPERTRANS_CJK_FONT to a local TTF, OTF, or TTC file."
            )

    @staticmethod
    def _first_existing(candidates: list[str | None]) -> Path | None:
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser().resolve()
            if path.is_file():
                return path
        return None

    def resolve(self, bold: bool = False) -> ResolvedCJKFont:
        path = self.bold_path if bold and self.bold_path else self.normal_path
        if path is None:
            raise RuntimeError("CJK font resolution failed")
        return ResolvedCJKFont(
            path=path,
            fontname="pt_cjk_bold" if bold else "pt_cjk_regular",
            bold=bold,
            metrics=pymupdf.Font(fontfile=str(path)),
        )

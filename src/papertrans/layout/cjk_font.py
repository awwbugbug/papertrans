from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pymupdf

DEFAULT_LANGUAGE = "zh-CN"

# Local Windows font families that cover each supported target language without
# bundling or downloading font files. First existing candidate wins.
_LANGUAGE_FONT_CANDIDATES: dict[str, tuple[list[str], list[str]]] = {
    "zh-CN": (
        ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"],
        ["C:/Windows/Fonts/msyhbd.ttc"],
    ),
    "zh-TW": (
        ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/mingliu.ttc"],
        ["C:/Windows/Fonts/msjhbd.ttc", "C:/Windows/Fonts/msyhbd.ttc"],
    ),
    "ja": (
        [
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/YuGothR.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
        ],
        ["C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryob.ttc"],
    ),
    "ko": (
        [
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/gulim.ttc",
            "C:/Windows/Fonts/batang.ttc",
        ],
        ["C:/Windows/Fonts/malgunbd.ttf"],
    ),
    # Latin and Cyrillic scripts (en, fr, es, de, ru, pt, ...): Arial covers both.
    "latin": (
        ["C:/Windows/Fonts/arial.ttf"],
        ["C:/Windows/Fonts/arialbd.ttf"],
    ),
}

# Languages whose scripts separate words with spaces and must break at word
# boundaries (Latin, Cyrillic, Korean) rather than between arbitrary characters.
_WORD_SEGMENTED_LANGUAGES = {
    "en",
    "fr",
    "es",
    "de",
    "ru",
    "pt",
    "it",
    "nl",
    "pl",
    "sv",
    "tr",
    "id",
    "vi",
    "ko",
}


def _base_code(language: str | None) -> str:
    return (language or "").strip().lower().split("-")[0]


def is_word_segmented(language: str | None) -> bool:
    """True when the target language separates words with spaces."""
    return _base_code(language) in _WORD_SEGMENTED_LANGUAGES


def _candidate_key(language: str | None) -> str:
    normalized = (language or "").strip()
    if normalized in {"zh-CN", "zh-Hans", "zh"}:
        return "zh-CN"
    if normalized in {"zh-TW", "zh-Hant"}:
        return "zh-TW"
    base = _base_code(normalized)
    if base == "zh":
        return "zh-CN"
    if base in {"ja", "ko"}:
        return base
    if base in _WORD_SEGMENTED_LANGUAGES:
        return "latin"
    return DEFAULT_LANGUAGE


@dataclass(frozen=True, slots=True)
class ResolvedCJKFont:
    path: Path
    fontname: str
    bold: bool
    metrics: pymupdf.Font


class CJKFontResolver:
    """Resolve a local font for the target language without bundling font files."""

    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self.language = language
        self._key = _candidate_key(language)
        normal_candidates, bold_candidates = _LANGUAGE_FONT_CANDIDATES[self._key]
        normal_override = os.environ.get("PAPERTRANS_CJK_FONT")
        bold_override = os.environ.get("PAPERTRANS_CJK_BOLD_FONT")
        self.normal_path = self._first_existing([normal_override, *normal_candidates])
        self.bold_path = self._first_existing(
            [
                bold_override,
                *bold_candidates,
                str(self.normal_path) if self.normal_path else None,
            ]
        )
        if self.normal_path is None:
            raise RuntimeError(
                "No local font found for target language "
                f"'{language}'. Set PAPERTRANS_CJK_FONT to a local TTF, OTF, or TTC file."
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

    def _fontname(self, bold: bool) -> str:
        tag = self._key.replace("-", "")
        return f"pt_{tag}_{'bold' if bold else 'regular'}"

    def resolve(self, bold: bool = False) -> ResolvedCJKFont:
        path = self.bold_path if bold and self.bold_path else self.normal_path
        if path is None:
            raise RuntimeError("CJK font resolution failed")
        return ResolvedCJKFont(
            path=path,
            fontname=self._fontname(bold),
            bold=bold,
            metrics=pymupdf.Font(fontfile=str(path)),
        )

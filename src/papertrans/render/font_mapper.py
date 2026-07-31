from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResolvedFont:
    fontname: str
    fontfile: str | None
    family: str
    bold: bool
    italic: bool

    @property
    def key(self) -> str:
        style = ("b" if self.bold else "r") + ("i" if self.italic else "n")
        return f"{self.family}-{style}"


class FontResolver:
    """Map embedded PDF font names to portable local or Base-14 fonts."""

    def __init__(self, windows_font_dir: str | Path = "C:/Windows/Fonts") -> None:
        self.windows_font_dir = Path(windows_font_dir)

    @staticmethod
    def _style(original_name: str, flags: int) -> tuple[str, bool, bool]:
        name = original_name.casefold().replace("+", "")
        bold = bool(flags & 16) or any(
            marker in name for marker in ("bold", "cmbx", "cmssbx", "-bd", "black")
        )
        italic = bool(flags & 2) or any(
            marker in name for marker in ("italic", "oblique", "cmti", "cmmi", "-it")
        )
        if any(marker in name for marker in ("courier", "mono", "cmtt")):
            family = "courier"
        elif any(marker in name for marker in ("helvetica", "arial", "sans", "cmss")):
            family = "arial"
        else:
            family = "times"
        return family, bold, italic

    def resolve(self, original_name: str, flags: int = 0) -> ResolvedFont:
        family, bold, italic = self._style(original_name, flags)
        style_suffix = {
            (False, False): "",
            (True, False): "bd",
            (False, True): "i",
            (True, True): "bi",
        }[(bold, italic)]
        filename = f"{family}{style_suffix}.ttf"
        font_path = self.windows_font_dir / filename
        if font_path.is_file():
            style = ("b" if bold else "r") + ("i" if italic else "n")
            return ResolvedFont(
                fontname=f"pt_{family}_{style}",
                fontfile=str(font_path),
                family=family,
                bold=bold,
                italic=italic,
            )

        builtin = {
            ("times", False, False): "tiro",
            ("times", True, False): "tibo",
            ("times", False, True): "tiit",
            ("times", True, True): "tibi",
            ("arial", False, False): "helv",
            ("arial", True, False): "hebo",
            ("arial", False, True): "heit",
            ("arial", True, True): "hebi",
            ("courier", False, False): "cour",
            ("courier", True, False): "cobo",
            ("courier", False, True): "coit",
            ("courier", True, True): "cobi",
        }[(family, bold, italic)]
        return ResolvedFont(
            fontname=builtin,
            fontfile=None,
            family=family,
            bold=bold,
            italic=italic,
        )

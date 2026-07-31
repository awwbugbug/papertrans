from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextStyle:
    font_name: str | None = None
    font_size: float | None = None
    color: int | None = None
    flags: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "font_name": self.font_name,
            "font_size": round(self.font_size, 3) if self.font_size is not None else None,
            "color": self.color,
            "flags": self.flags,
        }

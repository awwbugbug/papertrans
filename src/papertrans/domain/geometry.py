from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """A rectangle in PDF points, measured from the page's top-left corner."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    def to_list(self) -> list[float]:
        return [round(value, 3) for value in (self.x0, self.y0, self.x1, self.y1)]

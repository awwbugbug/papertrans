from __future__ import annotations

from pathlib import Path

import vtracer
from PIL import Image

REPOSITORY = Path(__file__).resolve().parents[1]
BRAND_ROOT = REPOSITORY / "assets" / "branding"
REFERENCE = BRAND_ROOT / "papertrans-icon-reference.png"
FLAT_PNG = BRAND_ROOT / "papertrans-icon.png"
SVG = BRAND_ROOT / "papertrans-icon.svg"

def build_flat_master() -> None:
    source = Image.open(REFERENCE).convert("RGBA")
    alpha = source.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise RuntimeError("PaperTrans icon reference is empty")
    cropped = source.crop(bounds)
    pixels = [
        (0, 0, 0, 0) if opacity <= 16 else (red, green, blue, opacity)
        for red, green, blue, opacity in cropped.get_flattened_data()
    ]
    cropped.putdata(pixels)
    cropped.thumbnail((820, 820), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    position = ((1024 - cropped.width) // 2, (1024 - cropped.height) // 2)
    canvas.alpha_composite(cropped, position)
    canvas.save(FLAT_PNG, optimize=True)


def build_svg() -> None:
    vtracer.convert_image_to_svg_py(
        str(FLAT_PNG),
        str(SVG),
        colormode="color",
        hierarchical="stacked",
        mode="polygon",
        filter_speckle=64,
        color_precision=8,
        layer_difference=16,
        corner_threshold=60,
        length_threshold=8,
        max_iterations=10,
        splice_threshold=45,
        path_precision=2,
    )


def main() -> None:
    build_flat_master()
    build_svg()
    print(SVG)


if __name__ == "__main__":
    main()

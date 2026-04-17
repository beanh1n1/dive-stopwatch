from __future__ import annotations

from pathlib import Path

from fontTools.misc.transform import Transform
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "fonts"
SOURCE = Path("/System/Library/Fonts/Menlo.ttc")
TEXT_FILE = ASSETS / "caisson_chars.txt"
OUTPUT = ASSETS / "CaissonCockpit.ttf"
GRID = 8
TARGETED_GLYPHS = {
    "zero": {"sx": 1.08, "sy": 0.98, "grid": 16},
    "one": {"sx": 0.92, "sy": 1.0, "grid": 16},
    "two": {"sx": 1.06, "sy": 0.99, "grid": 16},
    "three": {"sx": 1.06, "sy": 0.99, "grid": 16},
    "five": {"sx": 1.05, "sy": 1.0, "grid": 16},
    "seven": {"sx": 1.08, "sy": 0.98, "grid": 16},
    "eight": {"sx": 1.04, "sy": 0.98, "grid": 16},
    "A": {"sx": 1.02, "sy": 1.0, "grid": 16},
    "E": {"sx": 1.01, "sy": 1.0, "grid": 16},
    "F": {"sx": 1.01, "sy": 1.0, "grid": 16},
    "I": {"sx": 0.9, "sy": 1.0, "grid": 16},
    "M": {"sx": 1.08, "sy": 1.0, "grid": 16},
    "O": {"sx": 1.05, "sy": 0.98, "grid": 16},
    "R": {"sx": 1.03, "sy": 1.0, "grid": 16},
    "S": {"sx": 1.04, "sy": 0.99, "grid": 16},
    "T": {"sx": 1.04, "sy": 1.0, "grid": 16},
    "colon": {"sx": 0.92, "sy": 1.0, "grid": 16},
    "slash": {"sx": 1.05, "sy": 1.0, "grid": 16},
    "plus": {"sx": 1.04, "sy": 1.0, "grid": 16},
    "hyphen": {"sx": 1.08, "sy": 1.0, "grid": 16},
    "bar": {"sx": 0.84, "sy": 1.0, "grid": 16},
}


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    text = TEXT_FILE.read_text()

    collection = TTCollection(str(SOURCE))
    source_font = collection.fonts[0]
    source_font.save(OUTPUT)
    font = TTFont(OUTPUT, recalcBBoxes=True, recalcTimestamp=False)

    subsetter = Subsetter(options=Options())
    subsetter.populate(text=text)
    subsetter.subset(font)

    _rename_font(font)
    _cockpit_harden(font)

    font.save(OUTPUT)
    print(f"built {OUTPUT}")


def _rename_font(font: TTFont) -> None:
    updates = {
        1: "CaissonCockpit",
        3: "CaissonCockpit 1.0",
        4: "CaissonCockpit Regular",
        6: "CaissonCockpit-Regular",
        16: "CaissonCockpit",
        17: "Regular",
    }
    for record in font["name"].names:
        if record.nameID not in updates:
            continue
        text = updates[record.nameID]
        record.string = text.encode("utf-16-be") if record.isUnicode() else text.encode("ascii", errors="ignore")


def _cockpit_harden(font: TTFont) -> None:
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    transform_default = Transform().scale(1.02, 1.0)

    for glyph_name in font.getGlyphOrder():
        if glyph_name == ".notdef":
            continue
        glyph = glyf[glyph_name]
        if glyph.isComposite():
            continue
        if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
            continue

        coords, end_pts, flags = glyph.getCoordinates(glyf)
        if not coords:
            continue
        original_bounds = glyph.xMin, glyph.xMax, glyph.yMin, glyph.yMax
        profile = TARGETED_GLYPHS.get(glyph_name)
        transform = transform_default if profile is None else Transform().scale(profile["sx"], profile["sy"])
        transformed = GlyphCoordinates((transform.transformPoint((x, y)) for x, y in coords))
        transformed_bounds = _bounds(transformed)
        dx = ((original_bounds[0] + original_bounds[1]) - (transformed_bounds[0] + transformed_bounds[1])) / 2.0
        dy = ((original_bounds[2] + original_bounds[3]) - (transformed_bounds[2] + transformed_bounds[3])) / 2.0
        centered = GlyphCoordinates((x + dx, y + dy) for x, y in transformed)
        grid = profile["grid"] if profile is not None else GRID
        snapped = GlyphCoordinates((_snap(x, grid), _snap(y, grid)) for x, y in centered)
        glyph.coordinates = snapped
        glyph.endPtsOfContours = end_pts
        glyph.flags = flags
        glyph.recalcBounds(glyf)

        advance_width, left_side_bearing = hmtx[glyph_name]
        hmtx[glyph_name] = (advance_width, _snap(left_side_bearing, grid if profile is not None else GRID))

    # Tighten vertical metrics a touch for a denser panel feel.
    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.sTypoAscender = _snap(os2.sTypoAscender)
        os2.sTypoDescender = _snap(os2.sTypoDescender)
        os2.sTypoLineGap = 0


def _bounds(coords: GlyphCoordinates) -> tuple[float, float, float, float]:
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    return min(xs), max(xs), min(ys), max(ys)


def _snap(value: float, grid: int = GRID) -> int:
    return int(round(value / grid) * grid)


if __name__ == "__main__":
    main()

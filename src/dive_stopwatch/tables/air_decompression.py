"""Air decompression table lookups.

This first pass intentionally supports a cautious subset of Table 9-9:
exact AIR row lookups for 30, 35, 45, 50, 55, and 60 fsw. Values were
transcribed from the provided screenshots and should be treated as an exact
lookup table, not an interpolation engine.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AirDecoRow",
    "available_air_decompression_depths",
    "lookup_air_decompression_row",
]


@dataclass(frozen=True)
class AirDecoRow:
    depth_fsw: int
    bottom_time_min: int
    time_to_first_stop: str
    stops_fsw: dict[int, int]
    total_ascent_time: str
    chamber_o2_periods: float
    repeat_group: str | None
    section: str


AIR_DECOMPRESSION_TABLE: dict[int, dict[int, AirDecoRow]] = {
    30: {
        371: AirDecoRow(30, 371, "1:00", {}, "1:00", 0.0, "Z", "standard"),
        380: AirDecoRow(30, 380, "0:20", {20: 5}, "6:00", 0.5, "Z", "standard"),
        420: AirDecoRow(30, 420, "0:20", {20: 22}, "23:00", 0.5, "Z", "recommended"),
        480: AirDecoRow(30, 480, "0:20", {20: 42}, "43:00", 0.5, "Z", "recommended"),
        540: AirDecoRow(30, 540, "0:20", {20: 71}, "72:00", 1.0, None, "recommended"),
        600: AirDecoRow(30, 600, "0:20", {20: 92}, "93:00", 1.0, None, "required"),
        660: AirDecoRow(30, 660, "0:20", {20: 120}, "121:00", 1.0, None, "required"),
        720: AirDecoRow(30, 720, "0:20", {20: 158}, "159:00", 1.0, None, "required"),
    },
    35: {
        232: AirDecoRow(35, 232, "1:10", {}, "1:10", 0.0, "Z", "standard"),
        240: AirDecoRow(35, 240, "0:30", {20: 4}, "5:10", 0.5, "Z", "standard"),
        270: AirDecoRow(35, 270, "0:30", {20: 28}, "29:10", 0.5, "Z", "recommended"),
        300: AirDecoRow(35, 300, "0:30", {20: 53}, "54:10", 0.5, "Z", "recommended"),
        330: AirDecoRow(35, 330, "0:30", {20: 71}, "72:10", 1.0, "Z", "recommended"),
        360: AirDecoRow(35, 360, "0:30", {20: 88}, "89:10", 1.0, None, "recommended"),
        420: AirDecoRow(35, 420, "0:30", {20: 134}, "135:10", 1.5, None, "required"),
        480: AirDecoRow(35, 480, "0:30", {20: 173}, "174:10", 1.5, None, "required"),
        540: AirDecoRow(35, 540, "0:30", {20: 228}, "229:10", 2.0, None, "required"),
        600: AirDecoRow(35, 600, "0:30", {20: 277}, "278:10", 2.0, None, "required"),
        660: AirDecoRow(35, 660, "0:30", {20: 314}, "315:10", 2.5, None, "required"),
        720: AirDecoRow(35, 720, "0:30", {20: 342}, "343:10", 3.0, None, "required"),
    },
    45: {
        125: AirDecoRow(45, 125, "1:30", {}, "1:30", 0.0, "N", "standard"),
        130: AirDecoRow(45, 130, "0:50", {20: 2}, "3:30", 0.5, "O", "standard"),
        140: AirDecoRow(45, 140, "0:50", {20: 14}, "15:30", 0.5, "O", "standard"),
        150: AirDecoRow(45, 150, "0:50", {20: 25}, "26:30", 0.5, "Z", "recommended"),
        160: AirDecoRow(45, 160, "0:50", {20: 34}, "35:30", 0.5, "Z", "recommended"),
        170: AirDecoRow(45, 170, "0:50", {20: 41}, "42:30", 1.0, "Z", "recommended"),
        180: AirDecoRow(45, 180, "0:50", {20: 59}, "60:30", 1.0, "Z", "recommended"),
        190: AirDecoRow(45, 190, "0:50", {20: 71}, "72:30", 1.0, "Z", "recommended"),
        200: AirDecoRow(45, 200, "0:50", {20: 89}, "90:30", 1.0, "Z", "required"),
        210: AirDecoRow(45, 210, "0:50", {20: 107}, "102:30", 1.0, "Z", "required"),
        220: AirDecoRow(45, 220, "0:50", {20: 122}, "123:30", 1.5, "Z", "required"),
        230: AirDecoRow(45, 230, "0:50", {20: 130}, "131:30", 1.5, "Z", "required"),
        240: AirDecoRow(45, 240, "0:50", {20: 173}, "174:30", 2.0, None, "required"),
        300: AirDecoRow(45, 300, "0:50", {20: 206}, "207:30", 2.0, None, "required"),
        330: AirDecoRow(45, 330, "0:50", {20: 243}, "244:30", 2.5, None, "required"),
        360: AirDecoRow(45, 360, "0:50", {20: 288}, "289:30", 3.0, None, "required"),
        420: AirDecoRow(45, 420, "0:50", {20: 373}, "374:30", 3.5, None, "surd_o2_required"),
        480: AirDecoRow(45, 480, "0:50", {20: 431}, "432:30", 4.0, None, "surd_o2_required"),
        540: AirDecoRow(45, 540, "0:50", {20: 473}, "474:30", 4.5, None, "surd_o2"),
    },
    50: {
        92: AirDecoRow(50, 92, "1:40", {}, "1:40", 0.0, "M", "standard"),
        95: AirDecoRow(50, 95, "1:00", {20: 2}, "3:40", 0.5, "M", "standard"),
        100: AirDecoRow(50, 100, "1:00", {20: 4}, "5:40", 0.5, "N", "standard"),
        110: AirDecoRow(50, 110, "1:00", {20: 8}, "9:40", 0.5, "O", "standard"),
        120: AirDecoRow(50, 120, "1:00", {20: 21}, "22:40", 0.5, "O", "recommended"),
        130: AirDecoRow(50, 130, "1:00", {20: 34}, "35:40", 0.5, "Z", "recommended"),
        140: AirDecoRow(50, 140, "1:00", {20: 45}, "46:40", 1.0, "Z", "recommended"),
        150: AirDecoRow(50, 150, "1:00", {20: 56}, "57:40", 1.0, "Z", "recommended"),
        160: AirDecoRow(50, 160, "1:00", {20: 78}, "79:40", 1.0, "Z", "recommended"),
        170: AirDecoRow(50, 170, "1:00", {20: 96}, "97:40", 1.0, "Z", "required"),
        180: AirDecoRow(50, 180, "1:00", {20: 111}, "112:40", 1.5, "Z", "required"),
        190: AirDecoRow(50, 190, "1:00", {20: 125}, "126:40", 1.5, "Z", "required"),
        200: AirDecoRow(50, 200, "1:00", {20: 136}, "137:40", 1.5, "Z", "required"),
        210: AirDecoRow(50, 210, "1:00", {20: 147}, "148:40", 2.0, None, "required"),
        220: AirDecoRow(50, 220, "1:00", {20: 166}, "167:40", 2.0, None, "required"),
        230: AirDecoRow(50, 230, "1:00", {20: 183}, "184:40", 2.0, None, "required"),
        240: AirDecoRow(50, 240, "1:00", {20: 198}, "199:40", 2.0, None, "required"),
        270: AirDecoRow(50, 270, "1:00", {20: 236}, "237:40", 2.5, None, "required"),
        300: AirDecoRow(50, 300, "1:00", {20: 285}, "286:40", 3.0, None, "required"),
        330: AirDecoRow(50, 330, "1:00", {20: 345}, "346:40", 3.5, None, "surd_o2_required"),
        360: AirDecoRow(50, 360, "1:00", {20: 393}, "394:40", 3.5, None, "surd_o2_required"),
        420: AirDecoRow(50, 420, "1:00", {20: 464}, "465:40", 4.5, None, "surd_o2"),
    },
    55: {
        74: AirDecoRow(55, 74, "1:50", {}, "1:50", 0.0, "L", "standard"),
        75: AirDecoRow(55, 75, "1:10", {20: 1}, "2:50", 0.5, "L", "standard"),
        80: AirDecoRow(55, 80, "1:10", {20: 4}, "5:50", 0.5, "M", "standard"),
        90: AirDecoRow(55, 90, "1:10", {20: 10}, "11:50", 0.5, "N", "standard"),
        100: AirDecoRow(55, 100, "1:10", {20: 17}, "18:50", 0.5, "O", "recommended"),
        110: AirDecoRow(55, 110, "1:10", {20: 34}, "35:50", 0.5, "O", "recommended"),
        120: AirDecoRow(55, 120, "1:10", {20: 48}, "49:50", 1.0, "Z", "recommended"),
        130: AirDecoRow(55, 130, "1:10", {20: 59}, "60:50", 1.0, "Z", "recommended"),
        140: AirDecoRow(55, 140, "1:10", {20: 84}, "85:50", 1.0, "Z", "recommended"),
        150: AirDecoRow(55, 150, "1:10", {20: 105}, "106:50", 1.5, "Z", "required"),
        160: AirDecoRow(55, 160, "1:10", {20: 123}, "124:50", 1.5, "Z", "required"),
        170: AirDecoRow(55, 170, "1:10", {20: 138}, "139:50", 1.5, "Z", "required"),
        180: AirDecoRow(55, 180, "1:10", {20: 151}, "152:50", 2.0, "Z", "required"),
        190: AirDecoRow(55, 190, "1:10", {20: 169}, "170:50", 2.0, None, "required"),
        200: AirDecoRow(55, 200, "1:10", {20: 190}, "191:50", 2.0, None, "required"),
        210: AirDecoRow(55, 210, "1:10", {20: 208}, "209:50", 2.5, None, "required"),
        220: AirDecoRow(55, 220, "1:10", {20: 224}, "225:50", 2.5, None, "required"),
        230: AirDecoRow(55, 230, "1:10", {20: 239}, "240:50", 2.5, None, "required"),
        240: AirDecoRow(55, 240, "1:10", {20: 254}, "255:50", 3.0, None, "required"),
        270: AirDecoRow(55, 270, "1:10", {20: 313}, "314:50", 3.5, None, "required"),
        300: AirDecoRow(55, 300, "1:10", {20: 380}, "381:50", 3.5, None, "required"),
        330: AirDecoRow(55, 330, "1:10", {20: 432}, "433:50", 4.0, None, "required"),
        360: AirDecoRow(55, 360, "1:10", {20: 474}, "475:50", 4.5, None, "surd_o2"),
    },
    60: {
        63: AirDecoRow(60, 63, "2:00", {}, "2:00", 0.0, "K", "standard"),
        65: AirDecoRow(60, 65, "1:20", {20: 2}, "4:00", 0.5, "L", "standard"),
        70: AirDecoRow(60, 70, "1:20", {20: 7}, "9:00", 0.5, "L", "standard"),
        80: AirDecoRow(60, 80, "1:20", {20: 14}, "16:00", 0.5, "N", "standard"),
        90: AirDecoRow(60, 90, "1:20", {20: 23}, "25:00", 0.5, "O", "recommended"),
        100: AirDecoRow(60, 100, "1:20", {20: 42}, "44:00", 1.0, "Z", "recommended"),
        110: AirDecoRow(60, 110, "1:20", {20: 57}, "59:00", 1.0, "Z", "recommended"),
        120: AirDecoRow(60, 120, "1:20", {20: 75}, "77:00", 1.0, "Z", "recommended"),
        130: AirDecoRow(60, 130, "1:20", {20: 102}, "103:00", 1.5, "Z", "required"),
        140: AirDecoRow(60, 140, "1:20", {20: 124}, "126:00", 1.5, "Z", "required"),
        150: AirDecoRow(60, 150, "1:20", {20: 143}, "145:00", 2.0, "Z", "required"),
        160: AirDecoRow(60, 160, "1:20", {20: 158}, "160:00", 2.0, None, "required"),
        170: AirDecoRow(60, 170, "1:20", {20: 178}, "180:00", 2.0, None, "required"),
        180: AirDecoRow(60, 180, "1:20", {20: 201}, "203:00", 2.5, None, "required"),
        190: AirDecoRow(60, 190, "1:20", {20: 222}, "224:00", 2.5, None, "required"),
        200: AirDecoRow(60, 200, "1:20", {20: 240}, "242:00", 2.5, None, "required"),
        210: AirDecoRow(60, 210, "1:20", {20: 256}, "258:00", 3.0, None, "required"),
        220: AirDecoRow(60, 220, "1:20", {20: 278}, "280:00", 3.0, None, "required"),
        230: AirDecoRow(60, 230, "1:20", {20: 300}, "302:00", 3.5, None, "required"),
        240: AirDecoRow(60, 240, "1:20", {20: 321}, "323:00", 3.5, None, "required"),
        270: AirDecoRow(60, 270, "1:20", {20: 398}, "400:00", 4.0, None, "required"),
        300: AirDecoRow(60, 300, "1:20", {20: 456}, "458:00", 4.5, None, "surd_o2"),
    },
}


def available_air_decompression_depths() -> list[int]:
    return sorted(AIR_DECOMPRESSION_TABLE.keys())


def lookup_air_decompression_row(depth_fsw: int, bottom_time_min: int) -> AirDecoRow:
    depth_rows = AIR_DECOMPRESSION_TABLE.get(depth_fsw)
    if depth_rows is None:
        raise KeyError(f"Unsupported air decompression depth: {depth_fsw} fsw")

    row = depth_rows.get(bottom_time_min)
    if row is None:
        raise KeyError(
            f"Unsupported air decompression bottom time {bottom_time_min} min at {depth_fsw} fsw"
        )
    return row

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fontTools.ttLib import TTFont, newTable


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "fonts"
SOURCE_SFD = ASSETS / "CaissonCockpit-Regular.sfd"
OUTPUT = ASSETS / "CaissonCockpit.ttf"
FONTFORGE_PYTHON = Path("/Applications/FontForge.app/Contents/Frameworks/Python.framework/Versions/3.13/bin/python3.13")
FONTFORGE_SITE = Path("/Applications/FontForge.app/Contents/Resources/opt/local/lib/python3.13/site-packages")

NAME_RECORDS = {
    1: "CaissonCockpit",
    2: "Regular",
    3: "Version 1.0; Caisson Instruments; CaissonCockpit-Regular",
    4: "CaissonCockpit Regular",
    5: "Version 1.0",
    6: "CaissonCockpit-Regular",
    16: "CaissonCockpit",
    17: "Regular",
}


def main() -> None:
    if not SOURCE_SFD.exists():
        raise FileNotFoundError(f"Missing source font: {SOURCE_SFD}")
    ASSETS.mkdir(parents=True, exist_ok=True)
    _export_from_sfd()
    _ensure_metadata(OUTPUT)
    print(f"built {OUTPUT}")


def _export_from_sfd() -> None:
    if not FONTFORGE_PYTHON.exists() or not FONTFORGE_SITE.exists():
        raise FileNotFoundError(
            "FontForge runtime not found. Expected the macOS app bundle at "
            f"{FONTFORGE_PYTHON.parent.parent.parent.parent}"
        )
    code = (
        "import fontforge; "
        f"font = fontforge.open({str(SOURCE_SFD)!r}); "
        f"font.generate({str(OUTPUT)!r}); "
        "font.close()"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(FONTFORGE_SITE)
    subprocess.run(
        [str(FONTFORGE_PYTHON), "-c", code],
        check=True,
        env=env,
    )


def _ensure_metadata(path: Path) -> None:
    font = TTFont(path)

    if "name" not in font:
        font["name"] = newTable("name")
        font["name"].names = []

    name_table = font["name"]
    name_table.names = []
    for name_id, text in NAME_RECORDS.items():
        for platform_id, plat_enc_id, lang_id in (
            (3, 1, 0x409),
            (1, 0, 0),
        ):
            name_table.setName(text, name_id, platform_id, plat_enc_id, lang_id)

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.usWeightClass = 400
        os2.usWidthClass = 5

    if "head" in font:
        font["head"].fontRevision = 1.0

    font.save(path)


if __name__ == "__main__":
    main()

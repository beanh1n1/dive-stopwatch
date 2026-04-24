from __future__ import annotations

from pathlib import Path
import shutil

from fontTools.ttLib import TTFont, newTable


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "fonts"
SOURCE_TTF = ASSETS / "CaissonCockpit.ttf"
PACKAGE_ROOT = ASSETS / "CaissonCockpit-package"
DIST_ROOT = PACKAGE_ROOT / "dist"
WEB_ROOT = PACKAGE_ROOT / "web"
UPSTREAM_LICENSE = ASSETS / "UPSTREAM-DEJAVU-LICENSE.txt"


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
    if not SOURCE_TTF.exists():
        raise FileNotFoundError(f"Missing source font: {SOURCE_TTF}")

    shutil.rmtree(PACKAGE_ROOT, ignore_errors=True)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    WEB_ROOT.mkdir(parents=True, exist_ok=True)

    packaged_ttf = DIST_ROOT / "CaissonCockpit-Regular.ttf"
    shutil.copy2(SOURCE_TTF, packaged_ttf)
    _ensure_metadata(packaged_ttf)
    woff2_written = _write_woff2(packaged_ttf, DIST_ROOT / "CaissonCockpit-Regular.woff2")
    _write_web_css(woff2_written)
    _write_web_demo()
    if UPSTREAM_LICENSE.exists():
        shutil.copy2(UPSTREAM_LICENSE, PACKAGE_ROOT / "UPSTREAM-DEJAVU-LICENSE.txt")
    _write_readme()
    _write_license_notice()

    print(f"Packaged font at {PACKAGE_ROOT}")


def _ensure_metadata(path: Path) -> None:
    font = TTFont(path)

    if "name" not in font:
        font["name"] = newTable("name")
        font["name"].names = []

    name_table = font["name"]
    name_table.names = []
    for name_id, text in NAME_RECORDS.items():
        for platform_id, plat_enc_id, lang_id in (
            (3, 1, 0x409),  # Windows Unicode English
            (1, 0, 0),      # Macintosh Roman English
        ):
            name_table.setName(text, name_id, platform_id, plat_enc_id, lang_id)

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.usWeightClass = 400
        os2.usWidthClass = 5

    if "head" in font:
        font["head"].fontRevision = 1.0

    font.save(path)


def _write_woff2(source_ttf: Path, target_woff2: Path) -> bool:
    try:
        font = TTFont(source_ttf)
        font.flavor = "woff2"
        font.save(target_woff2)
        return True
    except Exception as exc:
        print(f"Skipping WOFF2 export: {exc}")
        return False


def _write_web_css(has_woff2: bool) -> None:
    src_lines = [
        'url("../dist/CaissonCockpit-Regular.ttf") format("truetype")',
    ]
    if has_woff2:
        src_lines.insert(0, 'url("../dist/CaissonCockpit-Regular.woff2") format("woff2")')
    css = f"""@font-face {{
  font-family: "CaissonCockpit";
  src:
    {",\n    ".join(src_lines)};
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}}
"""
    (WEB_ROOT / "caisson-cockpit.css").write_text(css)


def _write_web_demo() -> None:
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CaissonCockpit Demo</title>
    <link rel="stylesheet" href="./caisson-cockpit.css" />
    <style>
      body {
        margin: 0;
        padding: 32px;
        background: #0b0d12;
        color: #eef2f5;
        font-family: "CaissonCockpit", monospace;
      }
      .sample {
        font-size: 32px;
        line-height: 1.4;
        letter-spacing: 0.03em;
      }
      .small {
        margin-top: 24px;
        font-size: 18px;
      }
    </style>
  </head>
  <body>
    <div class="sample">DEPTH 145 FSW | NEXT 50 FSW FOR 03 MIN</div>
    <div class="small">0123456789 : / + - | AIR AIR/O2 STOPWATCH</div>
  </body>
</html>
"""
    (WEB_ROOT / "demo.html").write_text(html)


def _write_readme() -> None:
    text = """# CaissonCockpit Font Package

This is the standard cross-platform CaissonCockpit font package.

The current CaissonCockpit build is based on a custom-edited DejaVu Sans Mono
source, maintained in FontForge source form inside `assets/fonts/`.

## Included formats

- `dist/CaissonCockpit-Regular.ttf`
- optional `dist/CaissonCockpit-Regular.woff2` when Brotli is available
- `web/caisson-cockpit.css`
- `web/demo.html`

## Source

- FontForge source: `assets/fonts/CaissonCockpit-Regular.sfd`
- Upstream base: DejaVu Sans Mono
"""
    (PACKAGE_ROOT / "README.md").write_text(text)


def _write_license_notice() -> None:
    text = """CaissonCockpit is generated from a custom-edited DejaVu Sans Mono source.

Keep the upstream DejaVu license with this package when redistributing it.
"""
    (PACKAGE_ROOT / "LICENSE-NOTICE.txt").write_text(text)


if __name__ == "__main__":
    main()

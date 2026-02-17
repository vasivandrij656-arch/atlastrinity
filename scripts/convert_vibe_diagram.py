"""Convert Vibe SVG diagram into PNG and copy to architecture exports.

Usage: python3 scripts/convert_vibe_diagram.py

This is a best-effort converter: prefers cairosvg, falls back to rsvg-convert/ImageMagick,
or simply copies the SVG if conversion tools are not available.
"""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SRC_SVG = ROOT / "docs" / "vibe-usage-diagram.svg"
OUT_DIR = ROOT / "src" / "brain" / "data" / "architecture_diagrams" / "exports"
OUT_SVG = OUT_DIR / "vibe-usage-diagram.svg"
OUT_PNG = OUT_DIR / "vibe-usage-diagram.png"


def main() -> int:
    if not SRC_SVG.exists():
        print("No source SVG found at:", SRC_SVG)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_SVG, OUT_SVG)
    print(f"Copied SVG -> {OUT_SVG}")

    converted = False

    # Optional dependency: cairosvg. If it's not installed, fall back to CLI tools.
    try:
        import cairosvg  # type: ignore[reportMissingImports]
    except Exception:
        cairosvg = None  # type: ignore[assignment]

    if cairosvg:
        try:
            cairosvg.svg2png(url=str(SRC_SVG), write_to=str(OUT_PNG))
            converted = True
            print(f"Converted PNG -> {OUT_PNG} (via cairosvg)")
        except Exception:
            # continue to CLI fallbacks
            converted = False

    if not converted:
        # Try CLI fallbacks (rsvg-convert or ImageMagick `convert`)
        for cmd in (["rsvg-convert", "-o", str(OUT_PNG), str(SRC_SVG)],
                    ["convert", str(SRC_SVG), str(OUT_PNG)]):
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                converted = True
                print(f"Converted PNG -> {OUT_PNG} (via {' '.join(cmd)})")
                break
            except Exception:
                continue

    if not converted:
        print("PNG conversion not available — SVG copied to exports instead.")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_convert_vibe_diagram_creates_export():
    src_svg = PROJECT_ROOT / "docs" / "vibe-usage-diagram.svg"
    assert src_svg.exists(), "Source Vibe SVG must exist for this test"

    out_dir = PROJECT_ROOT / "src" / "brain" / "data" / "architecture_diagrams" / "exports"
    out_svg = out_dir / "vibe-usage-diagram.svg"
    out_png = out_dir / "vibe-usage-diagram.png"

    # Cleanup previous artifacts if any
    try:
        if out_svg.exists():
            out_svg.unlink()
        if out_png.exists():
            out_png.unlink()
    except Exception:
        pass

    # Run the conversion script
    res = subprocess.run([sys.executable, "scripts/convert_vibe_diagram.py"], cwd=str(PROJECT_ROOT))
    assert res.returncode == 0

    # SVG must be copied into exports
    assert out_svg.exists(), "Exported SVG should exist in architecture exports"

    # PNG is optional (best-effort); if present, ensure file exists
    if out_png.exists():
        assert out_png.stat().st_size > 0

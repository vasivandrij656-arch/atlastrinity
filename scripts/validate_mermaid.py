"""CI helper: validate Mermaid code blocks by rendering them with mermaid-cli (mmdc).

This script finds all ```mermaid``` fenced code blocks in the canonical
architecture markdown files and attempts to render each block using
`npx @mermaid-js/mermaid-cli`. Any rendering error fails the script (exit 1),
causing CI to flag invalid Mermaid syntax early.

Run locally:
    python scripts/validate_mermaid.py

"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

# Files to scan for mermaid blocks
TARGET_FILES = [
    Path("src/brain/data/architecture_diagrams/mcp_architecture.md"),
    Path(".agent/docs/mcp_architecture_diagram.md"),
    Path("docs/vibe-usage.md"),
]

MERMAID_FENCE = re.compile(r"```\s*mermaid\n([\s\S]*?)\n```", re.IGNORECASE)


def find_mermaid_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in MERMAID_FENCE.finditer(text)]


def render_mermaid_block(block: str, index: int, src_path: Path) -> None:
    # Write block to a temporary .mmd file and render via mmdc (npx)
    with tempfile.TemporaryDirectory() as td:
        mmd_path = Path(td) / f"block_{index}.mmd"
        out_png = Path(td) / f"block_{index}.png"
        mmd_path.write_text(block, encoding="utf-8")

        cmd = [
            "npx",
            "--yes",
            "@mermaid-js/mermaid-cli",
            "-i",
            str(mmd_path),
            "-o",
            str(out_png),
            "-b",
            "transparent",
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"\n[mermaid-validate] FAILED rendering block #{index} from {src_path}")
            print("--- command stdout ---")
            print(e.stdout)
            print("--- command stderr ---")
            print(e.stderr)
            raise


def main() -> int:
    failures = 0

    for path in TARGET_FILES:
        if not path.exists():
            # skip missing files (not all repos have docs/ present locally)
            continue

        text = path.read_text(encoding="utf-8")
        blocks = find_mermaid_blocks(text)
        if not blocks:
            print(f"[mermaid-validate] no mermaid blocks in {path}")
            continue

        print(f"[mermaid-validate] found {len(blocks)} mermaid block(s) in {path}")

        for i, block in enumerate(blocks, start=1):
            try:
                render_mermaid_block(block, i, path)
                print(f"[mermaid-validate] ok: {path} block #{i}")
            except Exception:
                failures += 1

    if failures:
        print(f"\n[mermaid-validate] completed with {failures} failure(s)")
        return 2

    print("\n[mermaid-validate] all mermaid blocks rendered successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

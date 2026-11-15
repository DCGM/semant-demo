"""Check that relative links in the project's Markdown point at existing files (#687).

Stdlib only; run from anywhere:  python scripts/check_doc_links.py

Checks every tracked ``*.md`` except generated and vendored ones. Links inside code
blocks and inline code, external URLs and in-page anchors are ignored; anchors after a
path are not checked (only that the path exists). Exits 1 listing each broken link.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = ("semant_demo_frontend/src/generated/",)
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
# [text](target) and ![alt](target "title"); reference definitions "[id]: target".
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|^\s*\[[^\]]+\]:\s*(\S+)", re.M)


def markdown_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    return sorted(f for f in out.split("\0") if f and not f.startswith(EXCLUDED))


def broken_links(relative: str) -> list[str]:
    path = ROOT / relative
    text = INLINE_CODE.sub("", FENCE.sub("", path.read_text(encoding="utf-8")))
    broken = []
    for match in LINK.finditer(text):
        target = match.group(1) or match.group(2)
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0].split("?", 1)[0]
        if not file_part:
            continue
        resolved = ROOT / file_part.lstrip("/") if file_part.startswith("/") else path.parent / file_part
        if not resolved.exists():
            broken.append(target)
    return broken


def main() -> int:
    files = markdown_files()
    failures = [(f, target) for f in files for target in broken_links(f)]
    for f, target in failures:
        print(f"{f}: broken link {target}")
    print(f"Checked relative links in {len(files)} Markdown files: {len(failures)} broken.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def anchors(path: Path) -> set[str]:
    result: set[str] = set()
    counts: dict[str, int] = {}
    for heading in HEADING.findall(path.read_text()):
        base = re.sub(r"[^\w\- ]", "", re.sub(r"<[^>]+>", "", heading.lower()))
        base = base.replace(" ", "-")
        count = counts.get(base, 0)
        counts[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


failures: list[str] = []
documents = [
    ROOT / "README.md",
    ROOT / "SPEC.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]
for document in documents:
    for raw_link in LINK.findall(document.read_text()):
        link = raw_link.strip().strip("<>")
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target_text, _, fragment = link.partition("#")
        target = (
            document
            if not target_text
            else (document.parent / unquote(target_text)).resolve()
        )
        if not target.exists():
            failures.append(f"{document.relative_to(ROOT)}: missing {link}")
        elif fragment and target.is_file() and unquote(fragment) not in anchors(target):
            failures.append(f"{document.relative_to(ROOT)}: missing anchor {link}")

if failures:
    raise SystemExit("\n".join(failures))
print(f"documentation links: {len(documents)} files passed")

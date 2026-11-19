"""Publish committed private notes and resolve only catalogued snapshots."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
from pathlib import Path
from typing import TypedDict, cast

from jarvis._atomic_json import replace_bytes

HOME_ORIGIN = "https://jarvis.nielseriknandal.com"
NOTES_ROOT = Path("/var/lib/jarvis-notes")
DEFAULT_EXPORT = NOTES_ROOT / ".git/jarvis-pages"
PAGE_CSP = (
    "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; "
    "form-action 'none'; base-uri 'none'; frame-ancestors 'self'"
)
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
REV_PATTERN = r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"


class _Work(TypedDict):
    current: str
    revisions: list[str]


class _Catalog(TypedDict):
    home: str | None
    works: dict[str, _Work]


def _catalog(root: Path) -> _Catalog:
    try:
        return cast(_Catalog, json.loads((root / "catalog.json").read_bytes()))
    except FileNotFoundError:
        if not root.is_dir():
            raise
        return {"home": None, "works": {}}


class HomePages:
    def __init__(self, root: Path = DEFAULT_EXPORT) -> None:
        self._root = root

    def home(self) -> dict[str, str] | None:
        catalog = _catalog(self._root)
        slug = catalog["home"]
        if slug is None:
            return None
        return {"kind": "view", "slug": slug, "rev": catalog["works"][slug]["current"]}

    def view(self, slug: str, rev: str | None = None) -> dict[str, str] | None:
        work = _catalog(self._root)["works"].get(slug)
        if work is None or (rev is not None and rev not in work["revisions"]):
            return None
        return {"kind": "view", "slug": slug, "rev": rev or work["current"]}

    def content(self, slug: str, rev: str) -> bytes | None:
        if self.view(slug, rev) is None:
            return None
        return (self._root / f"{slug}.{rev}.html").read_bytes()


def _publish(
    notes: Path, slug: str, rev: str | None, home: bool
) -> dict[str, str | bool]:
    if not re.fullmatch(SLUG_PATTERN, slug) or len(slug) > 64:
        raise ValueError("invalid page slug")
    root = notes / ".git/jarvis-pages"
    body: bytes | None = None
    if rev is not None:

        def git(*args: str) -> bytes:
            return subprocess.check_output(["git", "-C", str(notes), *args])

        if (
            not re.fullmatch(REV_PATTERN, rev)
            or git("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip() != rev
            or not git("for-each-ref", "--count=1", "--contains", rev, "refs/heads")
        ):
            raise ValueError("select a full commit reachable from a local branch")
        entry = git("ls-tree", "-l", rev, "--", f"site/{slug}/index.html").split()
        if len(entry) != 5 or entry[0] not in {b"100644", b"100755"}:
            raise ValueError("page requires a committed regular index.html")
        if int(entry[3]) > 16 * 1024 * 1024:
            raise ValueError("finished page exceeds 16 mib")
        body = git("cat-file", "blob", entry[2].decode("ascii"))
        body.decode("utf-8")

    lock = os.open(root, os.O_RDONLY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = _catalog(root)
        if rev is None:
            if slug in catalog["works"]:
                del catalog["works"][slug]
                if catalog["home"] == slug:
                    catalog["home"] = None
            else:
                return {"slug": slug, "published": False}
        else:
            assert body is not None
            path = root / f"{slug}.{rev}.html"
            if not path.exists():
                replace_bytes(path, body, 0o640)
            work = catalog["works"].setdefault(slug, {"current": rev, "revisions": []})
            if rev not in work["revisions"]:
                work["revisions"].append(rev)
            work["current"] = rev
            if home:
                catalog["home"] = slug
        replace_bytes(root / "catalog.json", json.dumps(catalog).encode(), 0o640)
    finally:
        os.close(lock)
    if rev is None:
        return {"slug": slug, "published": False}
    return {
        "slug": slug,
        "rev": rev,
        "url": f"{HOME_ORIGIN}/v/{slug}/{rev}",
        "is_home": catalog["home"] == slug,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("slug")
    publish.add_argument("commit")
    publish.add_argument("--home", action="store_true")
    commands.add_parser("withdraw").add_argument("slug")
    args = parser.parse_args()
    try:
        result = _publish(
            NOTES_ROOT,
            args.slug,
            getattr(args, "commit", None),
            getattr(args, "home", False),
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"jarvis-page: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

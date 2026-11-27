"""Publish committed private notes and resolve only catalogued editions."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Literal, Self, TypedDict

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from jarvis._atomic_json import replace_bytes
from jarvis.config import decode_config_json

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
_MAX_HTML = 16 * 1024 * 1024

type Slug = Annotated[str, Field(pattern=SLUG_PATTERN, max_length=64)]
type Revision = Annotated[str, Field(pattern=REV_PATTERN)]


class CatalogError(OSError):
    """The publication catalog cannot supply a trustworthy membership result."""


class CatalogRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


def _utc_stamp(value: str) -> str:
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)",
        value,
    ):
        raise ValueError("invalid UTC publication time")
    datetime.fromisoformat(value)
    return value


def _time_key(stamp: str | None) -> str:
    return (
        datetime.fromisoformat(stamp).isoformat(timespec="microseconds")
        if stamp
        else ""
    )


class Edition(CatalogRecord):
    rev: Revision
    title: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(min_length=1, max_length=240)] | None
    change: Annotated[str, Field(min_length=1, max_length=240)] | None
    published_at: Annotated[str, AfterValidator(_utc_stamp)] | None


def validate_current(slug: str, current: str, revisions: list[str]) -> None:
    if current not in revisions or len(set(revisions)) != len(revisions):
        raise ValueError(f"{slug} has an invalid current or duplicate edition")


class PublishedWork(CatalogRecord):
    current: Revision
    editions: list[Edition]


class CatalogFile(CatalogRecord):
    format: Literal[2]
    home: Slug | None
    works: dict[Slug, PublishedWork]

    @model_validator(mode="after")
    def validate_membership(self) -> Self:
        if self.home is not None and self.home not in self.works:
            raise ValueError("selected home is missing from the catalog")
        for slug, work in self.works.items():
            validate_current(slug, work.current, [item.rev for item in work.editions])
        return self


def read_catalog(root: Path) -> CatalogFile:
    data = (root / "catalog.json").read_bytes()
    try:
        return CatalogFile.model_validate(decode_config_json(data))
    except (ValueError, RecursionError) as error:
        raise CatalogError(f"invalid publication catalog: {error}") from error


class ShelfItem(TypedDict):
    slug: str
    current: str
    title: str
    description: str | None
    edition_count: int
    last_published_at: str | None


class CatalogSnapshot:
    def __init__(self, catalog: CatalogFile) -> None:
        self._catalog = catalog

    def home(self) -> dict[str, str] | None:
        slug = self._catalog.home
        return self.view(slug) if slug is not None else None

    def view(self, slug: str, rev: str | None = None) -> dict[str, str] | None:
        work = self._catalog.works.get(slug)
        if work is None or (
            rev is not None and not any(edition.rev == rev for edition in work.editions)
        ):
            return None
        return {"kind": "view", "slug": slug, "rev": rev or work.current}

    def listing(self) -> list[ShelfItem]:
        rows: list[ShelfItem] = []
        for slug, work in sorted(self._catalog.works.items()):
            current = next(
                edition for edition in work.editions if edition.rev == work.current
            )
            rows.append(
                {
                    "slug": slug,
                    "current": work.current,
                    "title": current.title,
                    "description": current.description,
                    "edition_count": len(work.editions),
                    "last_published_at": max(
                        (edition.published_at for edition in work.editions),
                        key=_time_key,
                    ),
                }
            )
        # Stable sorting retains ASCII slug order for ties, including undated works.
        rows.sort(key=lambda row: _time_key(row["last_published_at"]), reverse=True)
        return rows

    def work(self, slug: str) -> dict[str, object] | None:
        work = self._catalog.works.get(slug)
        if work is None:
            return None
        return {
            "slug": slug,
            "current": work.current,
            "editions": [edition.model_dump() for edition in reversed(work.editions)],
        }


class HomePages:
    def __init__(self, root: Path = DEFAULT_EXPORT) -> None:
        self._root = root

    def snapshot(self) -> CatalogSnapshot:
        return CatalogSnapshot(read_catalog(self._root))

    def view(self, slug: str, rev: str | None = None) -> dict[str, str] | None:
        return self.snapshot().view(slug, rev)

    def content(self, slug: str, rev: str) -> bytes | None:
        if self.view(slug, rev) is None:
            return None
        return read_export(self._root / f"{slug}.{rev}.html")


class _EndOfHead(Exception):
    pass


class _Head(HTMLParser):
    """Collect head metadata, excluding template contents and body text."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta: dict[str, str] = {}
        self._text_tag: str | None = None
        self._in_first_title = False
        self._templates = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "template":
            self._templates += 1
        elif self._templates or self._text_tag is not None:
            return
        elif tag in {"title", "script", "style", "noscript", "noframes"}:
            self._text_tag = tag
            self._in_first_title = tag == "title" and self.title is None
            if self._in_first_title:
                self.title = ""
        elif tag == "meta":
            fields = dict(reversed(attrs))
            name = (fields.get("name") or "").strip().lower()
            if name in {"description", "jarvis-change"}:
                self.meta.setdefault(name, fields.get("content") or "")
        elif tag not in {"html", "head", "base", "basefont", "bgsound", "link"}:
            raise _EndOfHead

    def handle_endtag(self, tag: str) -> None:
        if self._templates:
            self._templates -= int(tag == "template")
        elif tag == self._text_tag:
            self._text_tag = None
            self._in_first_title = False
        elif self._text_tag is None and tag in {"head", "body", "html"}:
            raise _EndOfHead

    def handle_data(self, data: str) -> None:
        if self._templates:
            return
        if self._in_first_title:
            assert self.title is not None
            self.title += data
        elif self._text_tag is None and data.strip():
            raise _EndOfHead


def _display(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def extract_edition(
    slug: str, rev: str, body: bytes, published_at: str | None
) -> Edition:
    head = _Head()
    html = body.decode("utf-8")
    with suppress(_EndOfHead):
        head.feed(html)
        head.close()
    return Edition(
        rev=rev,
        title=_display(head.title or "", 160) or slug.replace("-", " "),
        description=_display(head.meta.get("description", ""), 240) or None,
        change=_display(head.meta.get("jarvis-change", ""), 240) or None,
        published_at=published_at,
    )


def read_export(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_HTML:
        raise CatalogError(f"{path.name} requires a regular export within 16 mib")
    return path.read_bytes()


def replace_publication(path: Path, body: bytes) -> None:
    # The group bits set the mask of the inherited notes ACL. Named
    # writers need write access. The owning group and app remain readers.
    replace_bytes(path, body, 0o660)


@contextmanager
def publication_lock(root: Path, operation: int = fcntl.LOCK_EX) -> Iterator[None]:
    lock = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(lock, operation)
        yield
    finally:
        os.close(lock)


def _committed_html(notes: Path, slug: str, rev: str) -> bytes:
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
    if int(entry[3]) > _MAX_HTML:
        raise ValueError("finished page exceeds 16 mib")
    return git("cat-file", "blob", entry[2].decode("ascii"))


def _publish(
    notes: Path, slug: str, rev: str | None, home: bool
) -> dict[str, str | bool]:
    if not re.fullmatch(SLUG_PATTERN, slug) or len(slug) > 64:
        raise ValueError("invalid page slug")
    root = notes / ".git/jarvis-pages"
    body = _committed_html(notes, slug, rev) if rev is not None else None
    with publication_lock(root):
        catalog = read_catalog(root)
        work = catalog.works.get(slug)
        if rev is None:
            if work is None:
                return {"slug": slug, "published": False}
            del catalog.works[slug]
            if catalog.home == slug:
                catalog.home = None
        else:
            assert body is not None
            if work is None:
                work = PublishedWork(current=rev, editions=[])
                catalog.works[slug] = work
            admitted = any(edition.rev == rev for edition in work.editions)
            path = root / f"{slug}.{rev}.html"
            exists = path.exists()
            if (admitted or exists) and read_export(path) != body:
                raise CatalogError(f"{path.name} differs from its committed bytes")
            if not admitted:
                stamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                work.editions.append(extract_edition(slug, rev, body, stamp))
                if not exists:
                    replace_publication(path, body)
            work.current = rev
            if home:
                catalog.home = slug
        replace_publication(root / "catalog.json", catalog.model_dump_json().encode())
    if rev is None:
        return {"slug": slug, "published": False}
    return {
        "slug": slug,
        "rev": rev,
        "url": f"{HOME_ORIGIN}/artifacts/{slug}/{rev}",
        "is_home": catalog.home == slug,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("slug")
    publish.add_argument("commit")
    publish.add_argument("--home", action="store_true")
    commands.add_parser("withdraw").add_argument("slug")
    resolve = commands.add_parser("resolve")
    resolve.add_argument("slug")
    resolve.add_argument("rev", nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "resolve":
            result = HomePages().view(args.slug, args.rev)
            if result is None:
                raise ValueError("page is not published")
        elif args.command == "publish":
            result = _publish(NOTES_ROOT, args.slug, args.commit, args.home)
        else:
            result = _publish(NOTES_ROOT, args.slug, None, False)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"jarvis-page: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

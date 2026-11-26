"""Convert the private publication catalog under the named stopped cut."""

from __future__ import annotations

import argparse
import base64
import fcntl
import json
import sys
from hashlib import sha256
from pathlib import Path

from jarvis._atomic_json import replace_bytes
from jarvis.config import decode_config_json
from jarvis.home_pages import (
    DEFAULT_EXPORT,
    CatalogFile,
    CatalogRecord,
    Edition,
    PublishedWork,
    Revision,
    Slug,
    extract_edition,
    publication_lock,
    read_catalog,
    read_export,
    validate_current,
)


class _OldWork(CatalogRecord):
    current: Revision
    revisions: list[Revision]


class _OldCatalog(CatalogRecord):
    home: Slug | None
    works: dict[Slug, _OldWork]


class _Plan(CatalogRecord):
    preimage_b64: str | None
    preimage_sha256: str | None
    target_sha256: str
    members: dict[str, str]


def _plan(root: Path, source: bytes | None) -> tuple[_Plan, bytes]:
    old = (
        _OldCatalog.model_validate(decode_config_json(source))
        if source is not None
        else _OldCatalog(home=None, works={})
    )
    if old.home is not None and old.home not in old.works:
        raise ValueError("selected home is missing from the legacy catalog")
    members: dict[str, str] = {}
    works: dict[str, PublishedWork] = {}
    for slug, work in old.works.items():
        validate_current(slug, work.current, work.revisions)
        editions: list[Edition] = []
        for rev in work.revisions:
            name = f"{slug}.{rev}.html"
            body = read_export(root / name)
            editions.append(extract_edition(slug, rev, body, None))
            members[name] = sha256(body).hexdigest()
        works[slug] = PublishedWork(current=work.current, editions=editions)
    target = (
        CatalogFile(format=2, home=old.home, works=works).model_dump_json().encode()
    )
    return _Plan(
        preimage_b64=base64.b64encode(source).decode() if source is not None else None,
        preimage_sha256=sha256(source).hexdigest() if source is not None else None,
        target_sha256=sha256(target).hexdigest(),
        members=members,
    ), target


def _check_target(root: Path, empty: bool) -> dict[str, object]:
    catalog = read_catalog(root)
    if empty and (
        catalog.works or any(p.name != "catalog.json" for p in root.iterdir())
    ):
        raise ValueError("bootstrap requires an empty catalog and export directory")
    members = 0
    for slug, work in catalog.works.items():
        for edition in work.editions:
            read_export(root / f"{slug}.{edition.rev}.html").decode("utf-8")
            members += 1
    return {"status": "verified", "works": len(catalog.works), "members": members}


def _convert(
    command: str, root: Path, new_empty: bool, bound: _Plan | None
) -> dict[str, object]:
    path = root / "catalog.json"
    try:
        live = path.read_bytes()
    except FileNotFoundError:
        live = None
    if live is None and any(root.iterdir()):
        raise ValueError("catalog is missing in a populated export directory")

    if command == "plan":
        if new_empty != (live is None):
            raise ValueError(
                "new-empty requires a verified virgin installation with no catalog"
                if new_empty
                else "catalog is missing on an established installation"
            )
        plan, _ = _plan(root, live)
        return plan.model_dump()

    assert bound is not None
    source = (
        base64.b64decode(bound.preimage_b64, validate=True)
        if bound.preimage_b64 is not None
        else None
    )
    plan, target = _plan(root, source)
    if plan != bound:
        raise ValueError("frozen catalog digests or member exports differ")
    if live == target:
        status = "verified" if command == "verify" else "already applied"
    elif command == "apply" and live == source:
        replace_bytes(path, target, 0o640)
        if path.read_bytes() != target:
            raise ValueError("reopened catalog differs from the bound target")
        status = "applied"
    else:
        raise ValueError("catalog differs from the named cut's expected state")
    return {
        "status": status,
        "target_sha256": plan.target_sha256,
        "members": len(plan.members),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_EXPORT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan").add_argument("--new-empty", action="store_true")
    for verb in ("apply", "verify", "check", "check-empty"):
        commands.add_parser(verb)
    args = parser.parse_args()
    try:
        bound = None
        if args.command in {"apply", "verify"}:
            bound = _Plan.model_validate(decode_config_json(sys.stdin.buffer.read()))
        lock = fcntl.LOCK_EX if args.command == "apply" else fcntl.LOCK_SH
        with publication_lock(args.root, lock):
            if args.command in {"check", "check-empty"}:
                result = _check_target(args.root, empty=args.command == "check-empty")
            else:
                result = _convert(
                    args.command, args.root, getattr(args, "new_empty", False), bound
                )
    except (OSError, ValueError, RecursionError) as error:
        parser.exit(1, f"artifact catalog: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

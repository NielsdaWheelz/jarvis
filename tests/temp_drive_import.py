"""Temporary synthetic proof of deploy/drive-import against a local fake Google."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from jarvis.drive_cut import DriveCutManifest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = Path(
    os.environ.get("DRIVE_IMPORT_UNDER_TEST", ROOT / "deploy" / "drive-import")
)
WORK_ROOT = (
    Path.home()
    / ".local/state/jarvis/qualification/drive-files-implementation-2z9MM6fE"
    / "import-proof-work"
)
TOKEN = "ya29.synthetic-disposable-token-7f3a"
SUBJECT = "1234567890"
FOLDER = "folder_private_1"
SCOPES = "https://www.googleapis.com/auth/drive.file openid"


class Fake:
    """Enough of Drive v3 for the importer, with scripted faults."""

    def __init__(self) -> None:
        self.scopes = SCOPES
        self.sub = SUBJECT
        self.expires = 3600
        self.token = TOKEN
        self.about_permission = "perm-owner"
        self.folder: dict[str, object] = {
            "id": FOLDER,
            "mimeType": "application/vnd.google-apps.folder",
            "trashed": False,
            "ownedByMe": True,
            "shared": False,
            "permissions": [{"id": "perm-owner", "type": "user", "role": "owner"}],
        }
        self.files: dict[str, dict[str, object]] = {}
        self.sessions: dict[str, dict[str, object]] = {}
        self.log: list[tuple[str, str]] = []
        self.next_id = 0
        self.faults: list[str] = []  # consumed one per upload
        self.mutate: dict[str, object] = {}  # applied to stored file metadata
        self.corrupt = False
        self.squat: bytes | None = None
        self.on_upload = lambda meta: None  # type: ignore[assignment]
        self.quota_after: int | None = None
        self.uploads = 0

    def writes(self) -> list[tuple[str, str]]:
        return [
            entry
            for entry in self.log
            if entry[1] != "/tokeninfo"
            and (entry[0] != "GET" or entry[1].endswith("generateIds"))
        ]


def handler_for(fake: Fake) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def reply(
            self,
            status: int,
            body: object = None,
            raw: bytes | None = None,
            **headers: str,
        ) -> None:
            data = raw if raw is not None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            for key, value in headers.items():
                self.send_header(key.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(data)

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length", 0)))

        def authorized(self) -> bool:
            if self.headers.get("Authorization") == f"Bearer {fake.token}":
                return True
            self.reply(401, {"error": {"code": 401}})
            return False

        def do_POST(self) -> None:
            url = urlparse(self.path)
            fake.log.append(("POST", url.path))
            if url.path == "/tokeninfo":
                form = parse_qs(self.body().decode())
                if form.get("access_token") != [fake.token]:
                    return self.reply(400, {"error": "invalid_token"})
                return self.reply(
                    200,
                    {
                        "scope": fake.scopes,
                        "sub": fake.sub,
                        "aud": "client",
                        "exp": str(int(time.time()) + fake.expires),
                    },
                )
            if not self.authorized():
                return
            if url.path == "/upload/drive/v3/files":
                meta = json.loads(self.body())
                if meta["id"] in fake.files:
                    return self.reply(
                        409,
                        {"error": {"code": 409, "errors": [{"reason": "conflict"}]}},
                    )
                session = f"s{len(fake.sessions)}"
                fake.sessions[session] = meta
                return self.reply(
                    200,
                    {},
                    Location=f"http://127.0.0.1:{self.server.server_port}"
                    f"/upload/session/{session}",
                )
            self.reply(404, {})

        def do_PUT(self) -> None:
            url = urlparse(self.path)
            fake.log.append(("PUT", url.path))
            if not self.authorized():
                return
            meta = fake.sessions[url.path.rsplit("/", 1)[1]]
            data = self.body()
            fake.uploads += 1
            fault = fake.faults.pop(0) if fake.faults else ""
            if fault == "quota" or (
                fake.quota_after is not None and fake.uploads > fake.quota_after
            ):
                return self.reply(
                    403,
                    {
                        "error": {
                            "code": 403,
                            "errors": [{"reason": "storageQuotaExceeded"}],
                        }
                    },
                )
            if fault == "500_before_store":
                return self.reply(500, {"error": {"code": 500}})
            fake.on_upload(meta)
            if meta["id"] in fake.files:
                return self.reply(409, {"error": {"code": 409}})
            if fake.corrupt:
                data = b"X" + data[1:]
            stored = {
                "id": meta["id"],
                "name": meta["name"],
                "parents": meta["parents"],
                "mimeType": meta.get("mimeType"),
                "trashed": False,
                "ownedByMe": True,
                "shared": False,
                "bytes": data,
            } | fake.mutate
            fake.files[meta["id"]] = stored
            if fault == "drop_after_store":
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            self.reply(200, {"id": meta["id"]})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            fake.log.append(
                ("GET", url.path + ("?alt=media" if "alt" in query else ""))
            )
            if not self.authorized():
                return
            if url.path == "/drive/v3/about":
                return self.reply(
                    200, {"user": {"permissionId": fake.about_permission}}
                )
            if url.path == "/drive/v3/files/generateIds":
                ids = []
                for _ in range(int(query["count"][0])):
                    fake.next_id += 1
                    ids.append(f"gen_{fake.next_id:04d}")
                    if fake.squat is not None:
                        fake.files[ids[-1]] = {
                            "id": ids[-1],
                            "name": "squat",
                            "parents": ["elsewhere"],
                            "trashed": False,
                            "ownedByMe": True,
                            "shared": False,
                            "bytes": fake.squat,
                        }
                return self.reply(200, {"ids": ids, "space": "drive"})
            file_id = url.path.rsplit("/", 1)[1]
            if file_id == FOLDER:
                return self.reply(200, fake.folder)
            stored = fake.files.get(file_id)
            if stored is None:
                return self.reply(404, {"error": {"code": 404}})
            if "alt" in query:
                return self.reply(200, raw=stored["bytes"])  # type: ignore[arg-type]
            meta = {k: v for k, v in stored.items() if k != "bytes"}
            meta["size"] = str(len(stored["bytes"]))  # type: ignore[arg-type]
            self.reply(200, meta)

    return Handler


class Case:
    def __init__(self) -> None:
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        self.dir = Path(tempfile.mkdtemp(dir=WORK_ROOT))
        self.fake = Fake()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.fake))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.api = f"http://127.0.0.1:{self.server.server_port}"
        self.blobs = self.dir / "blobs"
        self.blobs.mkdir()
        self.token_file = self.dir / "token"
        self.token_file.write_text(TOKEN + "\n")
        self.token_file.chmod(0o600)
        self.state = self.dir / "map.jsonl"
        self.google_state = self.dir / "google-state.json"
        self.write_google_state({"status": "connected", "subject": SUBJECT})
        self.out = self.dir / "cut.json"
        self.outputs: list[str] = []
        self.rows: list[dict[str, object]] = []
        self.payloads: dict[str, bytes] = {}

    def write_google_state(self, grant: dict[str, object], mode: int = 0o600) -> None:
        self.google_state.write_text(json.dumps(grant))
        self.google_state.chmod(mode)

    def close(self) -> None:
        self.server.shutdown()
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(
        self,
        state: str,
        name: str | None = "a.pdf",
        data: bytes | None = b"%PDF-synthetic",
        reason: str | None = None,
        blob: bool = True,
    ) -> str:
        ident = str(uuid4())
        row: dict[str, object] = {
            "source_uuid": ident,
            "prior_state": state,
            "name": name,
            "size": None if data is None else len(data),
            "sha256": None if data is None else sha256(data).hexdigest(),
            "reason": reason,
        }
        if state in ("ready", "pending") and blob:
            (self.blobs / ident).write_bytes(data or b"")
            self.payloads[ident] = data or b""
        if state == "ready":
            row["media_type"] = "application/pdf"
        self.rows.append(row)
        return ident

    def standard(self) -> list[str]:
        return [
            self.add("ready", "a.pdf", b"%PDF-one"),
            self.add("ready", "a.pdf", b"%PDF-one"),  # duplicate name and bytes
            self.add("ready", "b.png", b"\x89PNG-two"),
            self.add("pending", "c.txt", b"pending spool"),
            self.add("failed", None, None, reason="NotFound"),
            self.add("deleted", "e.txt", b"gone", reason="owner deleted"),
        ]

    def write_inventory(self, **override: object) -> tuple[Path, str]:
        inventory = {
            "subject": SUBJECT,
            "parent": FOLDER,
            "rows": len(self.rows),
            "entries": self.rows,
        } | override
        path = self.dir / "inventory.json"
        path.write_text(json.dumps(inventory))
        return path, sha256(path.read_bytes()).hexdigest()

    def command(
        self,
        inventory_sha: str | None = None,
        extra: list[str] | None = None,
        **override: object,
    ) -> list[str]:
        path, digest = self.write_inventory(**override)
        return [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(path),
            "--inventory-sha256",
            inventory_sha or digest,
            "--blobs",
            str(self.blobs),
            "--token-file",
            str(self.token_file),
            "--state",
            str(self.state),
            "--out",
            str(self.out),
            "--google-state",
            str(self.google_state),
            "--api",
            self.api,
            "--tokeninfo",
            self.api + "/tokeninfo",
        ] + (extra or [])

    def start(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    def run(
        self,
        inventory_sha: str | None = None,
        extra: list[str] | None = None,
        **override: object,
    ) -> subprocess.CompletedProcess[str]:
        args = self.command(inventory_sha, extra, **override)
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        self.outputs += [result.stdout, result.stderr]
        assert TOKEN not in result.stdout + result.stderr, "token printed"
        return result

    def frozen(self) -> list[dict[str, object]]:
        if not self.state.exists():
            return []
        lines = self.state.read_text().splitlines()
        return [json.loads(line) for line in lines if line]

    def assert_untouched(self, result: subprocess.CompletedProcess[str]) -> None:
        assert result.returncode not in (0, 75), result.stderr
        assert not self.out.exists(), "output written"
        assert not self.fake.writes(), f"google written: {self.fake.writes()}"
        assert not self.state.exists(), "state written"


def ready(case: Case) -> list[dict[str, object]]:
    return [row for row in case.rows if row["prior_state"] == "ready"]


def test_happy_path() -> None:
    case = Case()
    try:
        case.standard()
        seen: list[str] = []

        def before_effect(meta: dict[str, object]) -> None:
            frozen = [r for r in case.frozen() if r.get("drive_id") == meta["id"]]
            assert len(frozen) == 1, "id not durable before upload"
            record = frozen[0]
            assert record["parent"] == FOLDER and record["subject"] == SUBJECT
            assert record["name"] == meta["name"]
            assert set(record) >= {"source_uuid", "size", "sha256"}
            seen.append(str(meta["id"]))

        case.fake.on_upload = before_effect
        result = case.run()
        assert result.returncode == 0, result.stderr
        assert len(seen) == 3
        manifest = DriveCutManifest.model_validate_json(case.out.read_text())
        assert manifest.subject == SUBJECT and manifest.parent == FOLDER
        assert [str(e.source_uuid) for e in manifest.entries] == [
            str(r["source_uuid"]) for r in case.rows
        ]
        by_uuid = {str(e.source_uuid): e for e in manifest.entries}
        for row in ready(case):
            entry = by_uuid[str(row["source_uuid"])]
            stored = case.fake.files[entry.drive_id]  # type: ignore[index]
            assert stored["bytes"] == case.payloads[str(row["source_uuid"])]
            assert stored["parents"] == [FOLDER] and stored["name"] == row["name"]
        assert len({e.drive_id for e in manifest.entries if e.drive_id}) == 3
        assert by_uuid[str(case.rows[3]["source_uuid"])].drive_id is None
        assert by_uuid[str(case.rows[4]["source_uuid"])].reason == "NotFound"
        assert oct(case.state.stat().st_mode & 0o777) == "0o600"
        assert oct(case.out.stat().st_mode & 0o777) == "0o600"
        # identity and folder are verified before any write; readback is fresh
        log = case.fake.log
        first_write = next(i for i, e in enumerate(log) if e[1].endswith("generateIds"))
        assert ("POST", "/tokeninfo") in log[:first_write]
        assert ("GET", f"/drive/v3/files/{FOLDER}") in log[:first_write]
        for drive_id in seen:
            assert ("GET", f"/drive/v3/files/{drive_id}?alt=media") in log
        assert str(sha256(case.state.read_bytes()).hexdigest()) in result.stdout
    finally:
        case.close()


def test_restart_reuses_frozen_id_after_lost_response() -> None:
    case = Case()
    try:
        case.add("ready", "a.pdf", b"%PDF-one")
        case.add("ready", "b.pdf", b"%PDF-two")
        case.fake.faults = ["", "drop_after_store"]
        first = case.run()
        assert first.returncode == 1 and not case.out.exists()
        frozen = {
            r["source_uuid"]: r["drive_id"] for r in case.frozen() if "drive_id" in r
        }
        assert len(frozen) == 2
        second = case.run()
        assert second.returncode == 0, second.stderr
        manifest = DriveCutManifest.model_validate_json(case.out.read_text())
        assert {str(e.source_uuid): e.drive_id for e in manifest.entries} == frozen
        assert len(case.fake.files) == 2 and case.fake.next_id == 2
        assert ("POST", "/upload/drive/v3/files") in case.fake.log
    finally:
        case.close()


def test_restart_after_failure_before_store() -> None:
    case = Case()
    try:
        case.add("ready")
        case.fake.faults = ["500_before_store"]
        assert case.run().returncode == 1
        frozen = [r["drive_id"] for r in case.frozen() if "drive_id" in r]
        assert len(frozen) == 1 and not case.fake.files
        assert case.run().returncode == 0
        assert list(case.fake.files) == frozen and case.fake.next_id == 1
    finally:
        case.close()


def test_conflict_with_wrong_bytes_refused() -> None:
    case = Case()
    try:
        case.add("ready")
        case.fake.squat = b"someone else's bytes"
        result = case.run()
        assert result.returncode == 1 and not case.out.exists()
        assert "mismatch" in result.stderr
    finally:
        case.close()


def test_readback_must_match_exactly() -> None:
    mutations = [
        ("bytes", {"corrupt": True}),
        ("name", {"name": "other.pdf"}),
        ("parent", {"parents": ["elsewhere"]}),
        ("two parents", {"parents": [FOLDER, "elsewhere"]}),
        ("trashed", {"trashed": True}),
        ("shared", {"shared": True}),
        ("owner", {"ownedByMe": False}),
    ]
    for label, mutation in mutations:
        case = Case()
        try:
            case.add("ready")
            if "corrupt" in mutation:
                case.fake.corrupt = True
            else:
                case.fake.mutate = mutation
            result = case.run()
            assert result.returncode == 1, label
            assert not case.out.exists(), label
            assert "mismatch" in result.stderr, label
        finally:
            case.close()


def test_quota_defers_and_resume_skips_verified() -> None:
    case = Case()
    try:
        first = case.add("ready", "a.pdf", b"%PDF-one")
        second = case.add("ready", "b.pdf", b"%PDF-two")
        case.fake.quota_after = 1
        deferred = case.run()
        assert deferred.returncode == 75, deferred.stderr
        assert "deferred" in deferred.stderr and not case.out.exists()
        ids = {
            r["source_uuid"]: r["drive_id"] for r in case.frozen() if "drive_id" in r
        }
        assert set(ids) == {first, second}
        case.fake.quota_after = None
        case.fake.log.clear()
        done = case.run()
        assert done.returncode == 0, done.stderr
        manifest = DriveCutManifest.model_validate_json(case.out.read_text())
        assert {str(e.source_uuid): e.drive_id for e in manifest.entries} == ids
        assert ("GET", f"/drive/v3/files/{ids[first]}?alt=media") not in case.fake.log
        assert case.fake.next_id == 2
    finally:
        case.close()


def test_identity_and_scopes_gate_every_write() -> None:
    bad = {
        "full drive scope": {"scopes": "https://www.googleapis.com/auth/drive openid"},
        "extra scope": {"scopes": SCOPES + " https://mail.google.com/"},
        "no drive.file": {"scopes": "openid"},
        "no subject scope": {"scopes": "https://www.googleapis.com/auth/drive.file"},
        "other subject": {"sub": "999"},
        "expired": {"expires": 5},
        "revoked token": {"token": "different"},
    }
    for label, change in bad.items():
        case = Case()
        try:
            case.standard()
            for key, value in change.items():
                setattr(case.fake, key, value)
            case.assert_untouched(case.run())
            fresh = Fake()
            for key in change:
                setattr(case.fake, key, getattr(fresh, key))
            assert case.run().returncode == 0, f"control run failed: {label}"
        finally:
            case.close()


def test_folder_must_be_verified_private_owner_only() -> None:
    owner = {"id": "perm-owner", "type": "user", "role": "owner"}
    bad = {
        "link sharing": {
            "permissions": [owner, {"id": "any", "type": "anyone", "role": "reader"}]
        },
        "second user": {
            "permissions": [owner, {"id": "u2", "type": "user", "role": "writer"}]
        },
        "not owner role": {
            "permissions": [{"id": "perm-owner", "type": "user", "role": "writer"}]
        },
        "foreign owner": {
            "permissions": [{"id": "perm-x", "type": "user", "role": "owner"}]
        },
        "shared flag": {"shared": True},
        "not mine": {"ownedByMe": False},
        "trashed": {"trashed": True},
        "not a folder": {"mimeType": "application/pdf"},
        "shared drive": {"driveId": "0Abc"},
        "no permission list": {"permissions": None},
    }
    for label, change in bad.items():
        case = Case()
        try:
            case.standard()
            case.fake.folder = case.fake.folder | change
            result = case.run()
            case.assert_untouched(result)
            assert "folder" in result.stderr, label
            case.fake.folder = Fake().folder
            assert case.run().returncode == 0, f"control run failed: {label}"
        finally:
            case.close()
    case = Case()
    try:
        case.standard()
        case.run(parent="some_other_folder")
        assert not case.fake.writes()
    finally:
        case.close()


def test_token_file_must_be_private() -> None:
    for label in ("mode 0644", "mode 0640", "symlink", "empty", "multiline"):
        case = Case()
        try:
            case.standard()
            if label == "mode 0644":
                case.token_file.chmod(0o644)
            elif label == "mode 0640":
                case.token_file.chmod(0o640)
            elif label == "symlink":
                real = case.dir / "real-token"
                real.write_text(TOKEN)
                real.chmod(0o600)
                case.token_file.unlink()
                case.token_file.symlink_to(real)
            elif label == "empty":
                case.token_file.write_text("")
            else:
                case.token_file.write_text(TOKEN + "\nsecond\n")
            result = case.run()
            case.assert_untouched(result)
            assert not case.fake.log, label
            case.token_file.unlink()
            case.token_file.write_text(TOKEN + "\n")
            case.token_file.chmod(0o600)
            assert case.run().returncode == 0, f"control run failed: {label}"
        finally:
            case.close()


def test_local_inputs_verified_before_any_effect() -> None:
    def fresh() -> Case:
        case = Case()
        case.standard()
        return case

    attempts: list[tuple[str, object]] = []

    case = fresh()
    attempts.append(("wrong inventory digest", (case, "0" * 64, {})))
    attempts.append(("row count short", (case, None, {"rows": 99})))
    dup = fresh()
    dup.rows.append(dict(dup.rows[0]))
    attempts.append(("duplicate source", (dup, None, {})))
    missing = fresh()
    (missing.blobs / str(ready(missing)[0]["source_uuid"])).unlink()
    attempts.append(("missing blob", (missing, None, {})))
    flipped = fresh()
    (flipped.blobs / str(ready(flipped)[0]["source_uuid"])).write_bytes(b"%PDF-onX")
    attempts.append(("blob digest", (flipped, None, {})))
    pending = fresh()
    (pending.blobs / str(pending.rows[3]["source_uuid"])).write_bytes(b"short")
    attempts.append(("pending spool digest", (pending, None, {})))
    invalid = fresh()
    invalid.rows[0]["name"] = None
    invalid.rows[0]["size"] = None
    invalid.rows[0]["sha256"] = None
    attempts.append(("ready without bytes", (invalid, None, {})))
    extra = fresh()
    extra.rows[0]["surprise"] = 1
    attempts.append(("unknown field", (extra, None, {})))
    try:
        for label, (target, digest_override, override) in attempts:  # type: ignore[misc]
            result = target.run(inventory_sha=digest_override, **override)
            try:
                target.assert_untouched(result)
                assert not target.fake.log, f"network touched: {label}"
            except AssertionError as error:
                raise AssertionError(f"{label}: {error}") from error
    finally:
        for target, _, _ in (a[1] for a in attempts):  # type: ignore[misc]
            target.close()


def test_state_discipline() -> None:
    case = Case()
    try:
        case.add("ready")
        result = case.run(
            extra=["--state", str(Path(tempfile.gettempdir()) / "map.jsonl")]
        )
        assert result.returncode not in (0, 75) and "scratch" in result.stderr
        assert not case.fake.writes()
    finally:
        case.close()

    # torn trailing record is discarded: its effect cannot have started
    case = Case()
    try:
        case.add("ready")
        case.fake.faults = ["500_before_store"]
        assert case.run().returncode == 1
        with case.state.open("a") as handle:
            handle.write('{"source_uuid": "tor')
        assert case.run().returncode == 0
    finally:
        case.close()

    # a frozen record that disagrees with the inventory is never reused
    case = Case()
    try:
        case.add("ready")
        case.fake.faults = ["500_before_store"]
        assert case.run().returncode == 1
        lines = [json.loads(line) for line in case.state.read_text().splitlines()]
        for record in lines:
            if "drive_id" in record:
                record["sha256"] = "0" * 64
        case.state.write_text("".join(json.dumps(r) + "\n" for r in lines))
        before = case.fake.uploads
        result = case.run()
        assert result.returncode == 1 and case.fake.uploads == before
        assert not case.out.exists()
    finally:
        case.close()


def test_plain_http_to_remote_host_refused() -> None:
    case = Case()
    try:
        case.add("ready")
        result = case.run(extra=["--api", "http://203.0.113.9"])
        case.assert_untouched(result)
        assert "https" in result.stderr
    finally:
        case.close()


def test_second_run_on_same_map_is_locked_out_before_any_id() -> None:
    case = Case()
    try:
        case.add("ready", "a.pdf", b"%PDF-one")
        case.add("ready", "b.pdf", b"%PDF-two")
        entered, release = threading.Event(), threading.Event()

        def stall(meta: dict[str, object]) -> None:
            if not entered.is_set():
                entered.set()
                release.wait(60)

        case.fake.on_upload = stall
        first = case.start()
        try:
            assert entered.wait(60), "first run never reached its upload"
            seen = len(case.fake.log)
            ids = case.fake.next_id
            second = case.run()
            assert second.returncode == 1, second.stderr
            assert "locked" in second.stderr
            assert len(case.fake.log) == seen and case.fake.next_id == ids == 1
        finally:
            release.set()
        stdout, stderr = first.communicate(timeout=60)
        assert first.returncode == 0, stderr
        assert TOKEN not in stdout + stderr
        sources = [r["source_uuid"] for r in case.frozen() if "verified_at" not in r]
        assert len(sources) == len(set(sources)) == 2 and len(case.fake.files) == 2
    finally:
        case.close()


def test_stopped_installation_subject_gates_the_import() -> None:
    bad = {
        "other subject": ({"status": "connected", "subject": "999"}, 0o600),
        "not connected": ({"status": "revoked", "subject": SUBJECT}, 0o600),
        "no subject": ({"status": "connected"}, 0o600),
        "mode 0644": ({"status": "connected", "subject": SUBJECT}, 0o644),
    }
    for label, (grant, mode) in bad.items():
        case = Case()
        try:
            case.standard()
            case.write_google_state(grant, mode)
            result = case.run()
            case.assert_untouched(result)
            assert not case.fake.log, f"network touched: {label}"
            assert "google state" in result.stderr, label
            case.write_google_state({"status": "connected", "subject": SUBJECT})
            assert case.run().returncode == 0, f"control run failed: {label}"
        finally:
            case.close()
    case = Case()
    try:
        case.standard()
        case.google_state.unlink()
        result = case.run()
        case.assert_untouched(result)
        assert not case.fake.log
    finally:
        case.close()


def test_absent_name_gets_a_derived_title_frozen_before_upload() -> None:
    for label, name in (("null", None), ("empty", "")):
        case = Case()
        try:
            source = case.add("ready", name, b"%PDF-one")
            case.add("ready", name, b"%PDF-one")  # same bytes, still separate
            result = case.run()
            assert result.returncode == 0, f"{label}: {result.stderr}"
            title = f"attachment-{source}"
            frozen = {
                r["source_uuid"]: r for r in case.frozen() if "verified_at" not in r
            }
            assert frozen[source]["name"] == title, label
            assert len({r["name"] for r in frozen.values()}) == 2, label
            manifest = DriveCutManifest.model_validate_json(case.out.read_text())
            entry = manifest.entries[0]
            assert entry.name == name and entry.drive_id, label  # history untouched
            stored = case.fake.files[entry.drive_id]
            assert stored["name"] == title and stored["bytes"] == b"%PDF-one", label
        finally:
            case.close()
    # the frozen title is the verified one: a tampered record is never reused
    case = Case()
    try:
        case.add("ready", None, b"%PDF-one")
        case.fake.faults = ["500_before_store"]
        assert case.run().returncode == 1
        lines = [json.loads(line) for line in case.state.read_text().splitlines()]
        for record in lines:
            record["name"] = "attachment-other"
        case.state.write_text("".join(json.dumps(r) + "\n" for r in lines))
        before = case.fake.uploads
        assert case.run().returncode == 1 and case.fake.uploads == before
    finally:
        case.close()
    # an upload that lands under another title fails readback
    case = Case()
    try:
        case.add("ready", None, b"%PDF-one")
        case.fake.mutate = {"name": "a.pdf"}
        result = case.run()
        assert result.returncode == 1 and "mismatch" in result.stderr
    finally:
        case.close()
    # the title is derived from one spelling of the uuid
    case = Case()
    try:
        case.add("ready", None, b"%PDF-one")
        case.rows[0]["source_uuid"] = str(case.rows[0]["source_uuid"]).upper()
        result = case.run()
        case.assert_untouched(result)
        assert not case.fake.log and "uuid" in result.stderr
    finally:
        case.close()


def test_target_type_is_normalised_and_frozen_before_allocation() -> None:
    octet = "application/octet-stream"
    cases = {
        "google-native": ("application/vnd.google-apps.document", octet),
        "native upper": ("Application/Vnd.Google-Apps.Folder", octet),
        "absent": (None, octet),
        "parameters": ("Text/Plain; charset=utf-8", "text/plain"),
        "malformed": ("not a type\r\nX-Evil: 1", octet),
        "plain": ("application/pdf", "application/pdf"),
    }
    for label, (given, expected) in cases.items():
        case = Case()
        try:
            case.add("ready", "a.bin", b"exact bytes")
            if given is None:
                del case.rows[0]["media_type"]
            else:
                case.rows[0]["media_type"] = given
            result = case.run()
            assert result.returncode == 0, f"{label}: {result.stderr}"
            frozen = [r for r in case.frozen() if "verified_at" not in r]
            assert [r["media_type"] for r in frozen] == [expected], label
            stored = case.fake.files[str(frozen[0]["drive_id"])]
            assert stored["mimeType"] == expected, label
            assert stored["bytes"] == b"exact bytes", label
        finally:
            case.close()
    case = Case()
    try:
        case.add("ready", "a.bin", b"exact bytes")
        case.fake.faults = ["500_before_store"]
        assert case.run().returncode == 1
        lines = [json.loads(line) for line in case.state.read_text().splitlines()]
        for record in lines:
            if "drive_id" in record:
                record["media_type"] = "text/html"
        case.state.write_text("".join(json.dumps(r) + "\n" for r in lines))
        before = case.fake.uploads
        assert case.run().returncode == 1 and case.fake.uploads == before
    finally:
        case.close()


TESTS = [
    test_happy_path,
    test_restart_reuses_frozen_id_after_lost_response,
    test_restart_after_failure_before_store,
    test_conflict_with_wrong_bytes_refused,
    test_readback_must_match_exactly,
    test_quota_defers_and_resume_skips_verified,
    test_identity_and_scopes_gate_every_write,
    test_folder_must_be_verified_private_owner_only,
    test_token_file_must_be_private,
    test_local_inputs_verified_before_any_effect,
    test_state_discipline,
    test_plain_http_to_remote_host_refused,
    test_second_run_on_same_map_is_locked_out_before_any_id,
    test_stopped_installation_subject_gates_the_import,
    test_absent_name_gets_a_derived_title_frozen_before_upload,
    test_target_type_is_normalised_and_frozen_before_allocation,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc(limit=4)
    print(f"{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())

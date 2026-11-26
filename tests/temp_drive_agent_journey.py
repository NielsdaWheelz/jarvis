"""Controlled redirect-free Drive MCP journey for ADR 0120. Temporary proof."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx

from jarvis.workspace_mcp import (
    DRIVE_SCOPE,
    WorkspaceApprovals,
    WorkspaceCredential,
    WorkspaceError,
    WorkspaceMcpClient,
)
from jarvis.workspace_reads import (
    Collection,
    DriveDownload,
    DriveItem,
    DriveSearch,
    DriveText,
    WorkspaceReadAccess,
    WorkspaceReads,
)
from jarvis.workspace_write_models import DriveSourceFile
from jarvis.workspace_writes import WorkspaceWriteConflict, WorkspaceWrites

ACCOUNT = "synthetic@example.test"
SUBJECT = "123456789"
GRANT = uuid4()
DRIVE_DOC = "application/vnd.google-apps.document"
FOLDER = "application/vnd.google-apps.folder"
PDF = "application/pdf"
RAW = b"%PDF-1.7\n" + b"o" * 500_000
OWNER = {"id": "owner", "role": "owner", "type": "user", "emailAddress": ACCOUNT}
READER = {"id": "group", "role": "reader", "type": "group", "emailAddress": "family@example.test"}


class Provider:
    def __init__(self):
        self.calls = []
        self.binary = {"pdf": RAW}
        self.items = {
            "root_id": self.file("root_id", "My Drive", FOLDER),
            "folder": self.file("folder", "taxes 2026", FOLDER, "root_id"),
            "pdf": self.file("pdf", "tax return.pdf", PDF, "folder", size=len(RAW)),
            "doc": self.file("doc", "memo", DRIVE_DOC, "folder"),
        }
        self.docs = {"doc": self.doc("doc", "rev0", "before\n")}
        self.permissions = {}
        self.fail_create = False
        self.fail_revise = False
        self.fail_docs = False
        self.bad_binary = False
        self.write_total = 0
        self.catalogs = {
            (product, method): json.loads(Path(
                f"/tmp/jarvis-0120-unit-a-public-{product}-{method.replace('/', '-')}.json"
            ).read_text())
            for product in ("drive", "docs")
            for method in ("server/discover", "tools/list")
        }

    @staticmethod
    def file(id, title, mime, parent=None, *, size=None, tag="etag0"):
        return {
            "id": id, "title": title, "mimeType": mime, "parentId": parent,
            "owner": ACCOUNT, "visibility": "PRIVATE", "etag": tag, "trashed": False,
            "fileSize": str(size) if size is not None else None,
        }

    @staticmethod
    def doc(id, revision, text):
        return {"documentId": id, "revisionId": revision, "body": {
            "content": [{"paragraph": {"elements": [{
                "startIndex": 1, "textRun": {"content": text},
            }]}}],
        }}

    async def response(self, request):
        content = await request.aread()
        if request.headers.get("Content-Length"):
            assert len(content) == int(request.headers["Content-Length"])
        data = json.loads(content)
        product = request.url.host.split("mcp.", 1)[0]
        method = data["method"]
        if (product, method) in self.catalogs:
            return httpx.Response(200, json=self.catalogs[product, method] | {"id": data["id"]})
        params = data["params"]
        tool = params["name"]
        args = params["arguments"]
        safe_args = {k: v for k, v in args.items() if k != "base64Content"}
        self.calls.append((tool, safe_args))
        id = args.get("fileId") or args.get("documentId")
        reply = {"resultType": "complete"}
        malformed_precondition = {
            "status": "FAILED_PRECONDITION", "code": 400,
        }
        if tool == "get_file_metadata":
            body = self.items["root_id" if id == "root" else id]
        elif tool == "get_file_permissions":
            body = {"permissions": self.permissions.get(id, [OWNER])}
        elif tool == "search_files":
            if args.get("pageToken") is not None:
                body = {"files": [self.items["pdf"], self.items["doc"]]}
            else:
                body = {"files": [self.items["pdf"], self.items["pdf"]], "nextPageToken": "page1"}
        elif tool == "list_recent_files":
            body = {"files": [self.items["doc"]]}
        elif tool == "read_file_content":
            body = {"fileContent": "tax return\n", "textFormattingNotSupported": True}
        elif tool == "download_file_content":
            payload = base64.b64encode(self.binary[id]).decode()
            blob = {"id": id, "title": self.items[id]["title"], "mimeType": PDF, "content": payload}
            reply["content"] = [{"type": "text", "text": json.dumps(blob)}]
            body = blob | {"content": "MQ==" if self.bad_binary else payload}
        elif tool == "read_doc":
            body = {"content": self.docs[id]}
        elif tool == "update_doc":
            self.write_total += 1
            assert args["writeControl"] == {
                "requiredRevisionId": "rev0", "writeMode": "SUGGEST",
            }
            if self.fail_docs:
                return httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": data["id"], "error": malformed_precondition},
                )
            self.docs[id] = self.doc(id, "rev1", "after\n")
            body = {"replies": [{}], "writeControl": {"requiredRevisionId": "rev1"}}
        elif tool == "create_file":
            self.write_total += 1
            id = f"new{self.write_total}"
            if "base64Content" in args:
                self.binary[id] = base64.b64decode(args["base64Content"], validate=True)
            if id in self.binary:
                mime, size = args["contentMimeType"], len(self.binary[id])
                assert args["disableConversionToGoogleType"] is True
            elif "mimeType" in args:
                mime, size = args["mimeType"], None
            else:
                mime, size = DRIVE_DOC, None
                self.docs[id] = self.doc(id, "newrev", args["textContent"] + "\n")
            self.items[id] = self.file(id, args["title"], mime, args["parentId"], size=size)
            if self.fail_create:
                raise httpx.ReadError("intentional reply loss", request=request)
            body = self.items[id]
        elif tool == "copy_file":
            self.write_total += 1
            copy = f"copy{self.write_total}"
            self.binary[copy] = self.binary[id]
            self.items[copy] = self.file(copy, args["title"], PDF, args["parentId"], size=len(self.binary[copy]))
            body = self.items[copy]
        elif tool == "upload_file_revision":
            self.write_total += 1
            assert args["etag"] == self.items[id]["etag"]
            if self.fail_revise:
                return httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": data["id"], "error": malformed_precondition},
                )
            self.binary[id] = base64.b64decode(args["base64Content"], validate=True)
            self.items[id]["fileSize"] = str(len(self.binary[id]))
            self.items[id]["etag"] = "etag1"
            body = {"id": "revision1", "fileEtag": "etag1"}
        else:
            raise AssertionError(tool)
        reply["structuredContent"] = body
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": data["id"], "result": reply})


async def test(path):
    provider = Provider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider.response)) as http:
        async def credential(grant, _):
            assert grant == GRANT
            return WorkspaceCredential("fake-drive-token", frozenset({DRIVE_SCOPE}))

        async def audit(_):
            raise AssertionError("no form in this fixture")

        async def debit(*_):
            raise AssertionError("no Gmail operations")

        async def fence(*_):
            pass

        async def materialize(source, size, digest):
            data = source.read()
            assert len(data) == size and sha256(data).hexdigest() == digest
            target = path / "native.pdf"
            target.write_bytes(data)
            return target

        mcp = WorkspaceMcpClient(
            http, credential=credential, debit=debit, approvals=WorkspaceApprovals(audit=audit),
        )
        reads = WorkspaceReads(
            mcp, account=ACCOUNT, subject=SUBJECT, grant_id=GRANT,
            access=lambda: WorkspaceReadAccess("inv", False, fence),
            drive_materialize=materialize, drive_download_qualified=True,
        )
        source_bytes = path / "chosen.pdf"
        source_bytes.write_bytes(RAW + b"revised")

        class Sources:
            @asynccontextmanager
            async def open(self, source, *, invocation_id, before_send):
                await before_send()
                data = source_bytes.read_bytes()
                yield DriveSourceFile(source_bytes, "chosen.pdf", PDF, len(data), sha256(data).hexdigest())

        writes = WorkspaceWrites(
            mcp, None, drive_sources=Sources(), drive_download_qualified=True,
            drive_revise_qualified=True, docs_update_qualified=True,
        )
        acks = []
        source = {"submission_id": str(uuid4())}

        async def ack(receipt):
            assert receipt.verification == "unverified"
            acks.append(receipt)

        async def prepare(tool, args):
            return await writes.prepare(
                tool, args, action_id=uuid4(), grant_id=GRANT, account=ACCOUNT,
                invocation_id="inv", before_send=fence, subject=SUBJECT,
            )

        async def execute(item):
            return await writes.execute(
                item, invocation_id="inv", before_send=fence, record_ack=ack,
            )

        p1 = await reads.read_drive("drive.search", DriveSearch(query="name contains 'tax'"))
        assert [item.id for item in p1.items] == ["pdf"]
        p2 = await reads.read_drive("drive.search", DriveSearch(query="name contains 'tax'", cursor=p1.next.cursor))
        assert [item.id for item in p2.items] == ["doc"] and p2.next is None
        assert (await reads.read_drive("drive.recent", Collection())).items[0].id == "doc"
        assert (await reads.read_drive("drive.get", DriveItem(id="pdf"))).items[0].etag == "etag0"
        assert (await reads.read_drive("drive.permissions", DriveItem(id="pdf"))).permissions[0].address == ACCOUNT
        assert "tax return" in (await reads.read_drive("drive.read", DriveText(id="pdf"))).chunk.text
        assert (await reads.read_drive("docs.read", DriveText(id="doc"))).revision == "rev0"
        download = await reads.read_drive("drive.download", DriveDownload(id="pdf"))
        assert Path(download.downloaded.path).read_bytes() == RAW
        provider.bad_binary = True
        try:
            await reads.read_drive("drive.download", DriveDownload(id="pdf"))
        except WorkspaceError as exc:
            assert exc.kind == "invalid_response"
        else:
            raise AssertionError("mismatched duplicated binary was accepted")
        provider.bad_binary = False

        create_args = {"parent": "folder", "name": "chosen.pdf", "source": source}
        create = await prepare("drive.create", create_args)
        assert create.effect.audience.private
        original_total = provider.write_total
        provider.permissions["root_id"] = [OWNER, READER]
        try:
            await execute(create)
        except WorkspaceWriteConflict as e:
            assert e.known_no_effect and e.kind == "drive_audience_changed"
        else:
            raise AssertionError("changed inherited audience did not stop effect")
        assert provider.write_total == original_total
        assert (await prepare("drive.create", create_args)).effect.audience.state == "shared"
        provider.permissions.clear()
        made = await execute(create)
        assert made.verification == "verified" and acks[-1].file_id == made.file_id
        assert provider.binary[made.file_id] == source_bytes.read_bytes()
        assert (await writes.recover_drive(create, acks[-1], invocation_id="repair", before_send=fence)).verification == "verified"

        provider.fail_create = True
        before = provider.write_total
        try:
            await execute(await prepare("drive.create", create_args))
        except WorkspaceError as e:
            assert e.kind == "uncertain" and not e.known_no_effect
        else:
            raise AssertionError("lost create acknowledgement was called a success")
        assert provider.write_total == before + 1
        provider.fail_create = False

        copied = await execute(await prepare("drive.copy", {
            "id": "pdf", "parent": "folder", "name": "copy.pdf",
        }))
        assert copied.verification == "verified" and copied.file_id != "pdf"
        revise = await prepare("drive.revise", {"id": "pdf", "etag": "etag0", "source": source})
        provider.fail_revise = True
        try:
            await execute(revise)
        except WorkspaceError as e:
            assert e.kind == "precondition_failed" and e.known_no_effect
        else:
            raise AssertionError("rival blob revision not rejected")
        provider.fail_revise = False
        revision = await execute(revise)
        assert revision.verification == "verified" and revision.revision == "revision1"
        assert revision.etag == "etag1" and provider.binary["pdf"] == source_bytes.read_bytes()

        doc = await execute(await prepare("drive.create", {
            "parent": "folder", "name": "new doc", "source": {"text": "hello"},
        }))
        assert doc.verification == "verified"
        updated = await execute(await prepare("docs.update", {
            "id": "doc", "revision": "rev0", "mode": "suggest",
            "requests": [{"insertText": {"location": {"index": 1}, "text": "after"}}],
        }))
        assert updated.verification == "verified" and updated.revision == "rev1"


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        asyncio.run(test(Path(directory)))

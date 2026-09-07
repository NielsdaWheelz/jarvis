from __future__ import annotations

from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from llm_tools import ToolId

ROOT = Path(__file__).resolve().parents[1]
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_writes.py"))
_Artifacts: Any = _QUALIFIER["_Artifacts"]
_QualificationFailure: Any = _QUALIFIER["QualificationFailure"]
_cleanup_external_artifacts = _QUALIFIER["_cleanup_external_artifacts"]
_assert_sanitized_output = _QUALIFIER["assert_sanitized_output"]
_OPERATIONS = cast("tuple[ToolId, ...]", _QUALIFIER["_OPERATIONS"])


class _Tokens:
    calls = 0

    async def access_token(self) -> tuple[str, int]:
        self.calls += 1
        return "synthetic-token", 0


def test_live_write_manifest_is_exact_and_excludes_gmail_send() -> None:
    assert _OPERATIONS == (
        ToolId("gmail.create_draft"),
        ToolId("gmail.update_draft"),
        ToolId("calendar.create_event"),
        ToolId("calendar.update_event"),
        ToolId("calendar.delete_event"),
    )
    assert ToolId("gmail.send_draft") not in _OPERATIONS


@pytest.mark.asyncio
async def test_cleanup_removes_both_live_artifact_kinds_without_retry() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-token"
        return httpx.Response(
            204 if "/drafts/" in request.url.path else 404,
            request=request,
        )

    tokens = _Tokens()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = await _cleanup_external_artifacts(
            client=client,
            tokens=cast("Any", tokens),
            artifacts=_Artifacts(
                calendar_id="owner@example.invalid",
                gmail_create_action_id=UUID("12345678-1234-4234-8234-123456789abc"),
                gmail_draft_id="synthetic/draft",
                calendar_event_id="synthetic/event",
            ),
        )

    assert result == {"calendar": True, "gmail": True}
    assert tokens.calls == 2
    assert [request.method for request in requests] == ["DELETE", "DELETE"]
    assert str(requests[0].url).endswith("/drafts/synthetic%2Fdraft")
    assert str(requests[1].url).startswith(
        "https://www.googleapis.com/calendar/v3/calendars/"
        "owner%40example.invalid/events/synthetic%2Fevent?"
    )
    assert requests[1].url.params["sendUpdates"] == "none"


@pytest.mark.asyncio
async def test_cleanup_attempts_calendar_after_gmail_cleanup_failure() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            500 if "/drafts/" in request.url.path else 204,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        with pytest.raises(_QualificationFailure) as raised:
            await _cleanup_external_artifacts(
                client=client,
                tokens=cast("Any", _Tokens()),
                artifacts=_Artifacts(
                    calendar_id="owner@example.invalid",
                    gmail_create_action_id=UUID("12345678-1234-4234-8234-123456789abc"),
                    gmail_draft_id="synthetic-draft",
                    calendar_event_id="synthetic-event",
                ),
            )

    assert len(requests) == 2
    assert raised.value.args == ("cleanup",)
    assert raised.value.stage == "cleanup"
    assert raised.value.reason == "external_cleanup_failed"


def test_sanitized_output_rejects_external_ids_and_credentials() -> None:
    clean = {
        "status": "passed",
        "writes": {"actions": 5, "cleanup": {"calendar": True, "gmail": True}},
    }
    _assert_sanitized_output(clean, ("synthetic-secret", "synthetic-id"))

    with pytest.raises(_QualificationFailure) as raised:
        _assert_sanitized_output(
            {"status": "failed", "private": "synthetic-id"},
            ("synthetic-secret", "synthetic-id"),
        )
    assert raised.value.reason == "private_value_exposed"


@pytest.mark.asyncio
async def test_unknown_created_draft_cannot_be_reported_as_clean() -> None:
    artifacts = _Artifacts(
        calendar_id="owner@example.invalid",
        gmail_create_action_id=UUID("12345678-1234-4234-8234-123456789abc"),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(204, request=request)
        ),
        trust_env=False,
    ) as client:
        result = await _cleanup_external_artifacts(
            client=client,
            tokens=cast("Any", _Tokens()),
            artifacts=artifacts,
        )

    assert result == {"calendar": True, "gmail": False}

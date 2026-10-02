"""Controlled Calendar handler fixtures; these never prove a remote mutation."""

from datetime import UTC, datetime

from llm_tools import (
    Available,
    CapabilityProfile,
    Native,
    NoDeclaredError,
    PolicyEpoch,
    ProfileId,
    PromptDocument,
    ReplayPolicy,
    RunLimits,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    ToolGrant,
    ToolId,
    ToolLimits,
    ToolPlan,
    ToolSpec,
)

from jarvis.action_requests import bind_action_requests
from jarvis.write_tools import (
    CalendarCreateEventInput,
    CalendarCreateEventSuccess,
    CalendarEventSnapshot,
)


def calendar_input():
    return CalendarCreateEventInput.model_validate(
        {
            "calendar_id": "proof-shared",
            "notify_attendees": True,
            "event": {
                "summary": "native authority proof",
                "description": None,
                "location": None,
                "start": {"type": "all_day", "date": "2026-10-03"},
                "end": {"type": "all_day", "date": "2026-10-04"},
                "recurrence": [],
                "attendees": [{"name": None, "address": "proof@example.com"}],
                "use_default_reminders": True,
                "reminders": [],
            },
        }
    )


def calendar_success(value):
    now = datetime.now(UTC)
    return CalendarCreateEventSuccess(
        event=CalendarEventSnapshot(
            calendar_id=value.calendar_id,
            event_id="controlled-proof",
            etag="controlled-etag",
            status="confirmed",
            writable=value.event,
            organizer=None,
            updated_at=now,
        ),
        created_at=now,
    )


def calendar_plan(handler):
    spec = ToolSpec(
        ToolId("calendar.create_event"),
        "controlled approved effect",
        PromptDocument("preserve exact Calendar input"),
        CalendarCreateEventInput,
        CalendarCreateEventSuccess,
        NoDeclaredError,
        ToolEffect.Write,
        ToolLimits(32768, 32768, 1, 30),
    )
    binding = ToolBinding(
        spec,
        Available(handler),
        ReplayPolicy.ReDispatchable,
        "proof-one",
        PolicyEpoch("proof-one"),
        {},
    )
    family = bind_action_requests(ToolFamily("calendar", (spec,), (binding,)))
    catalog = ToolCatalog.compose((family,))
    profile = CapabilityProfile(
        ProfileId("slice6_main"),
        (ToolGrant(spec.id, None),),
        RunLimits(None, None, None, None, 1, None),
    ).freeze(catalog)
    return ToolPlan(profile.id, Native()).freeze(catalog, profile)

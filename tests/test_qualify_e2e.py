from pathlib import Path
from runpy import run_path
from typing import Any, cast

from llm_tools import WebReadInput

from jarvis.read_tools import (
    CalendarGetEventInput,
    GmailReadThreadInput,
    MapsDirectionsInput,
    MapsGetPlaceInput,
    PlaceLocation,
)

_QUALIFIER = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "qualify_e2e.py")
)
_REQUIRED_COMPOUND_READS = cast(
    "frozenset[str]", _QUALIFIER["_REQUIRED_COMPOUND_READS"]
)
_RecordingDispatcher: Any = _QUALIFIER["_RecordingDispatcher"]


def test_compound_qualifier_requires_every_slice_2_read() -> None:
    assert _REQUIRED_COMPOUND_READS == {
        "gmail.search",
        "gmail.read_thread",
        "calendar.list_events",
        "calendar.get_event",
        "maps.search_places",
        "maps.get_place",
        "maps.directions",
        "web.search",
        "web.read",
    }


def test_compound_qualifier_requires_calendar_and_maps_search_linkage() -> None:
    dispatcher = _RecordingDispatcher(())
    dispatcher._record_success(
        tool_id="calendar.list_events",
        validated_input=object(),
        value={
            "events": [
                {"calendar_id": "primary", "event_id": "listed-event"},
            ]
        },
    )
    dispatcher._record_success(
        tool_id="calendar.get_event",
        validated_input=CalendarGetEventInput(
            calendar_id="primary",
            event_id="other-event",
        ),
        value={},
    )
    dispatcher._record_success(
        tool_id="maps.search_places",
        validated_input=object(),
        value={"places": [{"place_id": "listed-place"}]},
    )
    dispatcher._record_success(
        tool_id="maps.get_place",
        validated_input=MapsGetPlaceInput(place_id="other-place"),
        value={},
    )
    dispatcher._record_success(
        tool_id="maps.directions",
        validated_input=MapsDirectionsInput(
            origin=PlaceLocation(place_id="listed-place"),
            destination=PlaceLocation(place_id="other-place"),
            travel_mode="driving",
            departure_at=None,
        ),
        value={},
    )

    assert not dispatcher.calendar_linked
    assert not dispatcher.maps_get_linked
    assert not dispatcher.maps_directions_linked

    dispatcher._record_success(
        tool_id="calendar.get_event",
        validated_input=CalendarGetEventInput(
            calendar_id="primary",
            event_id="listed-event",
        ),
        value={},
    )
    dispatcher._record_success(
        tool_id="maps.get_place",
        validated_input=MapsGetPlaceInput(place_id="listed-place"),
        value={},
    )
    dispatcher._record_success(
        tool_id="maps.directions",
        validated_input=MapsDirectionsInput(
            origin=PlaceLocation(place_id="other-place"),
            destination=PlaceLocation(place_id="listed-place"),
            travel_mode="driving",
            departure_at=None,
        ),
        value={},
    )

    assert dispatcher.calendar_linked
    assert dispatcher.maps_get_linked
    assert dispatcher.maps_directions_linked

    dispatcher._record_success(
        tool_id="gmail.search",
        validated_input=object(),
        value={"threads": [{"thread_id": "listed-thread"}]},
    )
    dispatcher._record_success(
        tool_id="gmail.read_thread",
        validated_input=GmailReadThreadInput(
            thread_id="listed-thread",
            max_messages=1,
        ),
        value={},
    )
    dispatcher._record_success(
        tool_id="web.search",
        validated_input=object(),
        value={"results": [{"url": "https://example.com/read"}]},
    )
    dispatcher._record_success(
        tool_id="web.read",
        validated_input=WebReadInput(url="https://example.com/read"),
        value={},
    )

    assert dispatcher.compound_linkage_complete()

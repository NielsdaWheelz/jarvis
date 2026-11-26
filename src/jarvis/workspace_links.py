"""Keep only Google UI links bound to the exact observed resource."""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit


def workspace_link(
    value: object, product: str, resource: str, calendar: str = "", *, account: str = ""
) -> str | None:
    if (
        not isinstance(value, str)
        or len(value.encode()) > 4096
        or any(ord(c) < 33 for c in value)
    ):
        return None
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not resource:
            return None
        if (
            product == "gmail"
            and url.netloc == "mail.google.com"
            and re.fullmatch(r"/mail/(?:u/[^/]+/)?", url.path) is not None
        ):
            target = quote(resource, safe="")
            if url.fragment in {
                f"{name}/{target}"
                for name in (
                    "all",
                    "inbox",
                    "sent",
                    "drafts",
                    "trash",
                    "spam",
                    "starred",
                    "important",
                )
            }:
                if account:
                    owner = quote(account, safe="")
                    return f"https://mail.google.com/mail/u/{owner}/#all/{target}"
                return value if not url.query else None
            if url.fragment == f"drafts?compose={target}" and not url.query:
                if account:
                    owner = quote(account, safe="")
                    return f"https://mail.google.com/mail/u/{owner}/#drafts?compose={target}"
                return value
        if product == "calendar" and url.netloc in {
            "www.google.com",
            "calendar.google.com",
        }:
            if url.path not in {"/calendar/event", "/calendar/u/0/r/eventedit"}:
                return None
            params = parse_qs(url.query)
            ids = params.get("eid", ())
            if len(ids) != 1:
                return None
            encoded = ids[0]
            target = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            ).decode()
            cal = account if calendar == "primary" else calendar
            if cal and target == f"{resource} {cal}":
                eid = quote(encoded, safe="")
                return f"https://calendar.google.com/calendar/event?eid={eid}"
        if product == "drive" and re.fullmatch(r"[A-Za-z0-9_-]{1,255}", resource):
            parameters = parse_qs(url.query, max_num_fields=12)
            keys = parameters.get("resourcekey", [])
            if len(keys) > 1 or (
                keys and re.fullmatch(r"[A-Za-z0-9_-]{1,255}", keys[0]) is None
            ):
                return None
            query = "?" + urlencode({"resourcekey": keys[0]}) if keys else ""
            if url.netloc == "drive.google.com":
                if url.path in {
                    f"/file/d/{resource}/view",
                    f"/drive/folders/{resource}",
                }:
                    return f"https://drive.google.com{url.path}{query}"
                if url.path == "/open" and parameters.get("id") == [resource]:
                    query = urlencode(
                        {"id": resource} | ({"resourcekey": keys[0]} if keys else {})
                    )
                    return f"https://drive.google.com/open?{query}"
            if url.netloc == "docs.google.com" and re.fullmatch(
                rf"/(?:document|spreadsheets|presentation)/d/{resource}/(?:edit|view)",
                url.path,
            ):
                return f"https://docs.google.com{url.path}{query}"
    except (ValueError, UnicodeError):
        pass
    return None

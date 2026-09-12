#!/usr/bin/env python3
"""
excalidraw_invite.py -- Send Excalidraw+ workspace invites via the REST API.

Usage:
    python excalidraw_invite.py --email user@example.com --role member
    python excalidraw_invite.py --email user@example.com --role admin

Environment:
    EXCALIDRAW_API_KEY   Your Excalidraw+ API key (required)

Optional flags:
    --email   EMAIL   Recipient email address (required)
    --role    ROLE    member (default) or admin
    --dry-run         Print the request payload without sending
    --debug           Emit verbose HTTP details to stderr
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

# -- Constants ----------------------------------------------------------------

BASE_URL = "https://api.excalidraw.com/api/v1"
INVITES_ENDPOINT = f"{BASE_URL}/workspaces/invites"
VALID_ROLES = ("member", "admin")

# -- Logging ------------------------------------------------------------------

log = logging.getLogger("excalidraw_invite")


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))
    logging.getLogger().setLevel(level)
    log.addHandler(handler)
    log.propagate = False


# -- API client ---------------------------------------------------------------

class ExcalidrawAPIError(Exception):
    """Raised for non-2xx responses from the Excalidraw API."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self.body = body
        message = body.get("message", json.dumps(body))
        super().__init__(f"HTTP {status}: {message}")


@dataclass
class InviteResult:
    id: str
    created: str
    type: str
    status: str
    email: str | None
    role: str
    resolved_at: str | None
    redeemed_by: str | None
    max_uses: int | None
    uses: int
    restricted_domains: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InviteResult":
        return cls(
            id=d["id"],
            created=d["created"],
            type=d["type"],
            status=d["status"],
            email=d.get("email"),
            role=d["role"],
            resolved_at=d.get("resolvedAt"),
            redeemed_by=d.get("redeemedBy"),
            max_uses=d.get("maxUses"),
            uses=d.get("uses", 0),
            restricted_domains=d.get("restrictedDomains") or [],
        )


def _request(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated JSON request; raise ExcalidrawAPIError on failure."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode() if payload is not None else None

    log.debug("-> %s %s", method, url)
    if data:
        log.debug("  body: %s", data.decode())

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            log.debug("<- %s %s", resp.status, url)
            log.debug("  response: %s", raw.decode())
            return json.loads(raw)

    except urllib.error.HTTPError as exc:
        raw = exc.read()
        log.debug("<- HTTP error %s: %s", exc.code, raw.decode())
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"message": raw.decode() or exc.reason}
        raise ExcalidrawAPIError(exc.code, body) from exc

    except urllib.error.URLError as exc:
        raise SystemExit(f"Network error: {exc.reason}") from exc


def create_invite(api_key: str, email: str, role: str) -> InviteResult:
    payload = {"email": email, "role": role}
    data = _request("POST", INVITES_ENDPOINT, api_key, payload)
    return InviteResult.from_dict(data)


# -- CLI ----------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a workspace invite via the Excalidraw+ API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email address to invite.",
    )
    parser.add_argument(
        "--role",
        default="member",
        choices=VALID_ROLES,
        help="Role to assign (default: member).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the request payload without sending.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Emit verbose HTTP details to stderr.",
    )
    return parser.parse_args()


def _resolve_api_key() -> str:
    key = os.environ.get("EXCALIDRAW_API_KEY", "").strip()
    if not key:
        log.error(
            "EXCALIDRAW_API_KEY is not set.\n"
            "  Export it before running:\n"
            "    export EXCALIDRAW_API_KEY=sk-..."
        )
        sys.exit(1)
    return key


def main() -> None:
    args = _parse_args()
    _configure_logging(args.debug)

    api_key = _resolve_api_key()

    if args.dry_run:
        payload = {"email": args.email, "role": args.role}
        print("Dry run -- would POST to:", INVITES_ENDPOINT)
        print(json.dumps(payload, indent=2))
        return

    log.info("Sending invite to %s (role: %s)...", args.email, args.role)

    try:
        invite = create_invite(api_key, args.email, args.role)
    except ExcalidrawAPIError as exc:
        log.error("API error: %s", exc)
        if exc.status == 401:
            log.error("Check your EXCALIDRAW_API_KEY is valid and not expired.")
        elif exc.status == 403:
            log.error("Your API key does not have permission to manage invites.")
        sys.exit(1)

    print(
        json.dumps(
            {
                "id": invite.id,
                "status": invite.status,
                "email": invite.email,
                "role": invite.role,
                "type": invite.type,
                "created": invite.created,
                "uses": invite.uses,
                "maxUses": invite.max_uses,
            },
            indent=2,
        )
    )
    log.info("[x] Invite created: %s", invite.id)


if __name__ == "__main__":
    main()



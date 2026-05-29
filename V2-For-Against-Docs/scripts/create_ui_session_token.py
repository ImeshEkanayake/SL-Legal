#!/usr/bin/env python3
"""Create a signed V2 UI session token for private hosted-staging review."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time


USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
DEFAULT_COOKIE_NAME = "sl_legal_session"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=8 * 60 * 60)
    parser.add_argument("--secret", help="Session secret. Prefer environment variables outside local testing.")
    parser.add_argument("--cookie-name", default=os.getenv("SL_LEGAL_UI_SESSION_COOKIE_NAME", DEFAULT_COOKIE_NAME))
    parser.add_argument("--now-seconds", type=int)
    parser.add_argument("--output", choices=["token", "cookie", "json"], default="json")
    return parser.parse_args(argv)


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def session_secret(explicit_secret: str | None) -> str:
    secret = explicit_secret or os.getenv("SL_LEGAL_UI_SESSION_SECRET") or os.getenv("SL_LEGAL_AUTH_HMAC_SECRET") or ""
    if len(secret) < 32:
        raise SystemExit("SL_LEGAL_UI_SESSION_SECRET or SL_LEGAL_AUTH_HMAC_SECRET must be at least 32 characters.")
    return secret


def create_token(*, user_id: str, secret: str, now_seconds: int, ttl_seconds: int) -> str:
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise SystemExit("user id contains unsupported characters")
    if ttl_seconds < 60:
        raise SystemExit("ttl seconds must be at least 60")
    payload = {
        "version": 1,
        "userId": user_id,
        "issuedAt": now_seconds,
        "expiresAt": now_seconds + ttl_seconds,
    }
    encoded_payload = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = b64url(hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded_payload}.{signature}"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    now_seconds = args.now_seconds if args.now_seconds is not None else int(time.time())
    secret = session_secret(args.secret)
    token = create_token(
        user_id=args.user_id,
        secret=secret,
        now_seconds=now_seconds,
        ttl_seconds=args.ttl_seconds,
    )
    if args.output == "token":
        print(token)
    elif args.output == "cookie":
        print(f"{args.cookie_name}={token}; Path=/; HttpOnly; SameSite=Lax; Secure")
    else:
        print(
            json.dumps(
                {
                    "cookie_name": args.cookie_name,
                    "token": token,
                    "issued_at": now_seconds,
                    "expires_at": now_seconds + args.ttl_seconds,
                    "ttl_seconds": args.ttl_seconds,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request


USER_HEADER = "X-SL-Legal-User-ID"
TIMESTAMP_HEADER = "X-SL-Legal-Auth-Timestamp"
SIGNATURE_HEADER = "X-SL-Legal-Auth-Signature"
BODY_SHA256_HEADER = "X-SL-Legal-Body-SHA256"
AUTH_SECRET_ENV = "SL_LEGAL_AUTH_HMAC_SECRET"
AUTH_MAX_AGE_ENV = "SL_LEGAL_AUTH_MAX_AGE_SECONDS"
DEFAULT_MAX_AGE_SECONDS = 300
MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    timestamp: int
    body_sha256: str | None = None


async def require_auth_context(
    request: Request,
    x_sl_legal_user_id: str | None = Header(default=None, alias=USER_HEADER),
    x_sl_legal_auth_timestamp: str | None = Header(default=None, alias=TIMESTAMP_HEADER),
    x_sl_legal_auth_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    x_sl_legal_body_sha256: str | None = Header(default=None, alias=BODY_SHA256_HEADER),
) -> AuthContext:
    context = await optional_auth_context(
        request=request,
        x_sl_legal_user_id=x_sl_legal_user_id,
        x_sl_legal_auth_timestamp=x_sl_legal_auth_timestamp,
        x_sl_legal_auth_signature=x_sl_legal_auth_signature,
        x_sl_legal_body_sha256=x_sl_legal_body_sha256,
    )
    if context is None:
        raise HTTPException(status_code=401, detail="Authentication headers are required")
    return context


async def optional_auth_context(
    request: Request,
    x_sl_legal_user_id: str | None = Header(default=None, alias=USER_HEADER),
    x_sl_legal_auth_timestamp: str | None = Header(default=None, alias=TIMESTAMP_HEADER),
    x_sl_legal_auth_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    x_sl_legal_body_sha256: str | None = Header(default=None, alias=BODY_SHA256_HEADER),
) -> AuthContext | None:
    headers = [x_sl_legal_user_id, x_sl_legal_auth_timestamp, x_sl_legal_auth_signature]
    if not any(headers):
        return None
    if not all(headers):
        raise HTTPException(status_code=401, detail="Incomplete authentication headers")

    body = await request.body()
    actual_body_sha256 = hashlib.sha256(body).hexdigest()
    if x_sl_legal_body_sha256 is not None:
        provided_body_sha256 = _normalize_body_sha256(x_sl_legal_body_sha256)
        if not hmac.compare_digest(actual_body_sha256, provided_body_sha256):
            raise HTTPException(status_code=401, detail="Authentication body hash does not match request body")
    else:
        provided_body_sha256 = actual_body_sha256
    return authenticate_auth_headers(
        method=request.method,
        path=request.url.path,
        query_string=request.url.query,
        user_id=x_sl_legal_user_id,
        timestamp=x_sl_legal_auth_timestamp,
        signature=x_sl_legal_auth_signature,
        body_sha256=provided_body_sha256,
    )


def authenticate_auth_headers(
    *,
    method: str,
    path: str,
    query_string: str,
    user_id: str | None,
    timestamp: str | int | None,
    signature: str | None,
    body_sha256: str | None,
) -> AuthContext:
    if not user_id or timestamp is None or not signature or not body_sha256:
        raise HTTPException(status_code=401, detail="Incomplete authentication headers")

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise HTTPException(status_code=401, detail="Authenticated user ID is empty")
    try:
        parsed_timestamp = int(str(timestamp))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Authentication timestamp is invalid") from exc
    _validate_timestamp(parsed_timestamp)

    normalized_body_sha256 = _normalize_body_sha256(body_sha256)
    expected_signature = sign_auth_request(
        method=method,
        path=path,
        query_string=query_string,
        user_id=normalized_user_id,
        timestamp=parsed_timestamp,
        body_sha256=normalized_body_sha256,
        secret=_auth_secret(),
    )
    if not hmac.compare_digest(expected_signature, str(signature)):
        raise HTTPException(status_code=401, detail="Authentication signature is invalid")
    return AuthContext(user_id=normalized_user_id, timestamp=parsed_timestamp, body_sha256=normalized_body_sha256)


def sign_auth_request(
    *,
    method: str,
    path: str,
    query_string: str,
    user_id: str,
    timestamp: int,
    secret: str,
    body: bytes | None = None,
    body_sha256: str | None = None,
) -> str:
    resolved_body_sha256 = _body_sha256(body=body, body_sha256=body_sha256)
    payload = "\n".join(
        [
            method.upper(),
            path,
            query_string,
            user_id,
            str(timestamp),
            resolved_body_sha256,
        ]
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _auth_secret() -> str:
    secret = os.getenv(AUTH_SECRET_ENV, "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise HTTPException(
            status_code=500,
            detail=f"{AUTH_SECRET_ENV} must be set to at least {MIN_SECRET_LENGTH} characters",
        )
    return secret


def _body_sha256(*, body: bytes | None, body_sha256: str | None) -> str:
    if body is None and body_sha256 is None:
        raise ValueError("Either body or body_sha256 is required")
    if body_sha256 is None:
        return hashlib.sha256(body or b"").hexdigest()
    normalized_body_sha256 = _normalize_body_sha256(body_sha256)
    if body is not None and not hmac.compare_digest(hashlib.sha256(body).hexdigest(), normalized_body_sha256):
        raise ValueError("body_sha256 does not match body")
    return normalized_body_sha256


def _normalize_body_sha256(body_sha256: str) -> str:
    normalized = str(body_sha256).strip().lower()
    if len(normalized) != 64:
        raise HTTPException(status_code=401, detail=f"{BODY_SHA256_HEADER} must be a SHA-256 hex digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"{BODY_SHA256_HEADER} must be a SHA-256 hex digest") from exc
    return normalized


def _validate_timestamp(timestamp: int) -> None:
    max_age = int(os.getenv(AUTH_MAX_AGE_ENV, str(DEFAULT_MAX_AGE_SECONDS)))
    now = int(time.time())
    if abs(now - timestamp) > max_age:
        raise HTTPException(status_code=401, detail="Authentication timestamp is outside the allowed window")

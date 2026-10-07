import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash

from app.core.config import settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise HTTPException(status_code=422, detail="Password must contain at least 10 characters")
    return password_hash.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return password_hash.verify(password, hashed)


def credential_fingerprint(hashed: str | None) -> str:
    if not hashed:
        return "no-password"
    return hashlib.sha256(hashed.encode("utf-8")).hexdigest()[:32]


def create_access_token(user_id: UUID, current_password_hash: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "cv": credential_fingerprint(current_password_hash),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_access_payload(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        UUID(payload["sub"])
        return payload
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


def decode_access_token(token: str) -> UUID:
    payload = _decode_access_payload(token)
    return UUID(payload["sub"])


def validate_access_token_credential(token: str, current_password_hash: str | None) -> None:
    payload = _decode_access_payload(token)
    if payload.get("cv") != credential_fingerprint(current_password_hash):
        raise HTTPException(status_code=401, detail="Session expired after credential change")


def auth_is_required() -> bool:
    return settings.auth_required or settings.environment.lower() == "production"

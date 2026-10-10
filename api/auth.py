"""Account registration and opaque bearer-token authentication."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.storage import (
    create_auth_token,
    create_auth_user,
    delete_auth_token,
    get_auth_identity,
    get_auth_user_by_email,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
TOKEN_TTL_SECONDS = 12 * 60 * 60
PASSWORD_ITERATIONS = 310_000


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    session_id: str
    demo_session_id: str
    email: str


class AuthIdentity(BaseModel):
    user_id: str
    email: str
    session_id: str
    demo_session_id: str


def _password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_token(authorization: str | None) -> tuple[AuthIdentity, str] | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if len(token) < 32 or len(token) > 256:
        return None
    digest = _token_digest(token)
    identity = get_auth_identity(digest, int(time.time()))
    if identity is None:
        return None
    identity_payload = dict(identity)
    identity_payload["demo_session_id"] = f"demo-{identity_payload['user_id']}"
    return AuthIdentity.model_validate(identity_payload), digest


def _issue_token(user: dict[str, str]) -> AuthResponse:
    token = secrets.token_urlsafe(48)
    create_auth_token(_token_digest(token), user["user_id"], int(time.time()) + TOKEN_TTL_SECONDS)
    return AuthResponse(
        access_token=token,
        expires_in=TOKEN_TTL_SECONDS,
        session_id=user["session_id"],
        demo_session_id=f"demo-{user['user_id']}",
        email=user["email"],
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(body: Credentials) -> AuthResponse:
    salt = secrets.token_bytes(16)
    user = {
        "user_id": str(uuid.uuid4()),
        "email": body.email,
        "session_id": str(uuid.uuid4()),
    }
    created = create_auth_user(
        user["user_id"],
        user["email"],
        salt.hex(),
        _password_digest(body.password, salt).hex(),
        user["session_id"],
        datetime.now(timezone.utc).isoformat(),
    )
    if not created:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return _issue_token(user)


@router.post("/login", response_model=AuthResponse)
def login(body: Credentials) -> AuthResponse:
    user = get_auth_user_by_email(body.email)
    # Perform the password hash even for unknown emails to reduce timing-based enumeration.
    salt = bytes.fromhex(user["password_salt"]) if user else b"spendshield-dummy-salt"
    expected = bytes.fromhex(user["password_hash"]) if user else bytes(32)
    valid = hmac.compare_digest(_password_digest(body.password, salt), expected)
    if user is None or not valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return _issue_token(user)


@router.get("/me", response_model=AuthIdentity)
def current_user(authorization: str | None = Header(default=None)) -> AuthIdentity:
    authenticated = authenticate_token(authorization)
    if authenticated is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return authenticated[0]


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)) -> None:
    authenticated = authenticate_token(authorization)
    if authenticated is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    delete_auth_token(authenticated[1])

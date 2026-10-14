"""Password hashing and JWT helpers shared by every route module."""

import hashlib
import hmac
import os
import time

import jwt
from fastapi import Depends, Header, HTTPException

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"


def hash_password(raw: str, salt: bytes) -> str:
    """Derive a PBKDF2 hash for a plaintext password."""
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, 120_000).hex()


def verify_password(raw: str, salt: bytes, expected: str) -> bool:
    return hmac.compare_digest(hash_password(raw, salt), expected)


def create_access_token(user_id: int, ttl_seconds: int = 3600) -> str:
    """Issue a signed JWT that expires after ttl_seconds."""
    claims = {"sub": str(user_id), "exp": int(time.time()) + ttl_seconds}
    return jwt.encode(claims, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Validate signature and expiry; raises 401 on any problem."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc


def get_current_user(authorization: str = Header(None)) -> dict:
    """Resolve the bearer token on the request into the calling user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    claims = decode_access_token(authorization.removeprefix("Bearer "))
    return {"id": int(claims["sub"])}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Gate for admin-only routes: 403 unless the user has the admin role."""
    if user["id"] not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="admin only")
    return user


ADMIN_IDS = {1}

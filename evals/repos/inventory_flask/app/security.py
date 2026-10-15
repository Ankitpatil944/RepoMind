import functools
import hashlib
import hmac
import os

import jwt
from flask import g, jsonify, request

SECRET = os.environ.get("SECRET_KEY", "dev")


def hash_password(password: str, salt: str = "inventory") -> str:
    """PBKDF2 hash of a password with a fixed application salt."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def verify_password(password: str, expected: str) -> bool:
    return hmac.compare_digest(hash_password(password), expected)


def issue_token(user_id: int, role: str) -> str:
    return jwt.encode({"sub": user_id, "role": role}, SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"])


def login_required(view):
    """Reject the request unless it carries a valid bearer token."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        try:
            g.user = decode_token(header.removeprefix("Bearer "))
        except jwt.InvalidTokenError:
            return jsonify(error="unauthorized"), 401
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    """Like login_required, and the token must carry the admin role."""

    @login_required
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.user.get("role") != "admin":
            return jsonify(error="forbidden"), 403
        return view(*args, **kwargs)

    return wrapper

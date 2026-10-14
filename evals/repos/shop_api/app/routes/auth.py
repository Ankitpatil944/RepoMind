from fastapi import APIRouter, Depends, HTTPException

from app.db import run_query
from app.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.services.emailer import send_password_reset

router = APIRouter(prefix="/auth")


@router.post("/login")
def login(email: str, password: str):
    """Exchange an email and password for an access token."""
    rows = run_query("SELECT id, salt, password_hash FROM users WHERE email = %s", (email,))
    if not rows or not verify_password(password, rows[0][1], rows[0][2]):
        raise HTTPException(status_code=401, detail="bad credentials")
    return {"access_token": create_access_token(rows[0][0])}


@router.post("/register")
def register(email: str, password: str):
    """Create a new account with a salted password hash."""
    salt = email.encode()[:16].ljust(16, b"0")
    run_query(
        "INSERT INTO users (email, salt, password_hash) VALUES (%s, %s, %s)",
        (email, salt, hash_password(password, salt)),
    )
    return {"ok": True}


@router.post("/refresh")
def refresh(user=Depends(get_current_user)):
    """Issue a fresh token for an already-authenticated user."""
    return {"access_token": create_access_token(user["id"])}


@router.post("/forgot-password")
def forgot_password(email: str):
    send_password_reset(email, reset_token="TODO")
    return {"ok": True}


@router.post("/logout")
def logout(user=Depends(get_current_user)):
    return {"ok": True, "user": user["id"]}

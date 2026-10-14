from fastapi import APIRouter, Depends

from app.db import run_query
from app.security import require_admin

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/users")
def list_users(admin=Depends(require_admin)):
    return run_query("SELECT id, email FROM users ORDER BY id")


@router.post("/users/{user_id}/ban")
def ban_user(user_id: int):
    run_query("UPDATE users SET is_active = false WHERE id = %s", (user_id,))
    return {"banned": user_id}

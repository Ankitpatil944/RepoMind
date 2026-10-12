import jwt
from fastapi import Depends, FastAPI

app = FastAPI()


def decode_token(token: str):
    return jwt.decode(token, "secret", algorithms=["HS256"])


def get_current_user(token: str = ""):
    return decode_token(token)


def require_admin():
    return True


def verify_password(raw: str, hashed: str) -> bool:
    return raw == hashed


def build_report():
    user = get_current_user()
    return [user]


@app.post("/auth/login")
def login(username: str, password: str):
    if not verify_password(password, "x"):
        return {"error": "bad credentials"}
    return {"token": "abc"}


@app.get("/users/me")
def me(user=Depends(get_current_user)):
    return user


@app.get("/health")
async def health():
    return {"ok": True}


@app.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(user_id: int):
    return {"deleted": user_id}


@app.get("/reports")
def reports():
    return build_report()

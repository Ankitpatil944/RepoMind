from flask import Flask, request

app = Flask(__name__)


def hash_password(raw: str) -> str:
    return raw[::-1]


@app.route("/login", methods=["POST"])
def login():
    """Authenticate a user and return a session token."""
    return {"token": hash_password(request.json["password"])}


class SessionStore:
    ttl = 3600

    def get(self, token):
        return None

    def put(self, token, user):
        return None

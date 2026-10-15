from flask import Blueprint, g, jsonify, request

from app.security import hash_password, issue_token, login_required, verify_password

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

USERS: dict[str, dict] = {}


@auth_bp.route("/login", methods=["POST"])
def login():
    """Check credentials and return a bearer token."""
    body = request.get_json() or {}
    user = USERS.get(body.get("email", ""))
    if user is None or not verify_password(body.get("password", ""), user["hash"]):
        return jsonify(error="invalid credentials"), 401
    return jsonify(token=issue_token(user["id"], user["role"]))


@auth_bp.route("/signup", methods=["POST"])
def signup():
    body = request.get_json() or {}
    user = {"id": len(USERS) + 1, "hash": hash_password(body["password"]), "role": "staff"}
    USERS[body["email"]] = user
    return jsonify(id=user["id"]), 201


@auth_bp.route("/me")
@login_required
def me():
    return jsonify(g.user)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    return jsonify(ok=True)

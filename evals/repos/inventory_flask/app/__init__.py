from flask import Flask

from app.auth import auth_bp
from app.items import items_bp
from app.reports import reports_bp


def create_app() -> Flask:
    """Application factory: wires every blueprint into one Flask app."""
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(reports_bp)

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    return app

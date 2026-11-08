import sqlite3

from flask import Flask, jsonify, send_from_directory

from .config import Config
from .db import close_db, connect, migrate
from .errors import register_error_handlers


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["APP_CONFIG"] = config or Config.from_env()
    app.config["JSON_SORT_KEYS"] = False

    db = connect(app.config["APP_CONFIG"].database_path)
    migrate(db)
    db.close()

    app.teardown_appcontext(close_db)
    register_error_handlers(app)

    from .api import admin, auth, directory, public, workflow
    for module in (auth, public, directory, workflow, admin):
        app.register_blueprint(module.bp, url_prefix="/api")

    @app.errorhandler(sqlite3.IntegrityError)
    def handle_integrity_error(err):
        app.logger.warning("Integrity error: %s", err)
        return jsonify({"error": {"code": "CONSTRAINT_VIOLATION",
                                  "message": "The change conflicts with existing data or database rules"}}), 409

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        if response.mimetype == "application/json":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app

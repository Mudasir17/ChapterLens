import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import inspect, text

from app.extensions import db, login_manager
from app.models import User


def _ensure_schema_compatibility() -> None:
    inspector = inspect(db.engine)
    book_columns = {c["name"] for c in inspector.get_columns("books")}
    summary_columns = {c["name"] for c in inspector.get_columns("summaries")}

    statements = []
    if "processing_status" not in book_columns:
        statements.append(
            "ALTER TABLE books ADD COLUMN processing_status VARCHAR(24) NOT NULL DEFAULT 'processing'"
        )
    if "processing_error" not in book_columns:
        statements.append("ALTER TABLE books ADD COLUMN processing_error TEXT")
    if "processed_at" not in book_columns:
        statements.append("ALTER TABLE books ADD COLUMN processed_at DATETIME")
    if "model_name" not in summary_columns:
        statements.append(
            "ALTER TABLE summaries ADD COLUMN model_name VARCHAR(120) NOT NULL DEFAULT 'fallback-extractive'"
        )
    if "created_at" not in summary_columns:
        statements.append("ALTER TABLE summaries ADD COLUMN created_at DATETIME")

    for stmt in statements:
        db.session.execute(text(stmt))
    if statements:
        db.session.commit()


def _init_markdown(app: Flask) -> None:
    """Register a Jinja2 {{ value | markdown }} filter."""
    import markdown as md_lib
    import markupsafe

    @app.template_filter("markdown")
    def render_markdown(text: str) -> markupsafe.Markup:
        if not text:
            return markupsafe.Markup("")
        html = md_lib.markdown(text, extensions=["extra", "nl2br"])
        return markupsafe.Markup(html)


def create_app() -> Flask:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
    instance_path = Path(__file__).resolve().parent.parent / "instance"
    instance_path.mkdir(parents=True, exist_ok=True)
    default_sqlite = f"sqlite:///{instance_path / 'library.db'}"
    db_url = os.environ.get("DATABASE_URL", default_sqlite)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "32")) * 1024 * 1024
    upload_dir = Path(__file__).resolve().parent.parent / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = str(upload_dir)

    db.init_app(app)
    login_manager.init_app(app)

    # Register markdown filter for templates
    _init_markdown(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        if not user_id or not user_id.isdigit():
            return None
        return db.session.get(User, int(user_id))

    from app.auth import bp as auth_bp
    from app.main import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()
        _ensure_schema_compatibility()

    return app
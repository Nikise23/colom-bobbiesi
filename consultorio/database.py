"""Inicialización de la base de datos PostgreSQL."""

import os

from consultorio.extensions import db


def init_db(app) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        import consultorio.models  # noqa: F401 — registra modelos en SQLAlchemy
        # El esquema lo gestiona Alembic (pre-deploy: scripts/render_predeploy.py)

"""Revision ID: 008_dias_especiales_web

Días/períodos especiales para turnos web de un médico.
"""

from alembic import op
import sqlalchemy as sa


revision = "008_dias_especiales_web"
down_revision = "007_bloqueo_periodo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dias_especiales_web",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medico", sa.String(length=255), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("fecha", sa.String(length=30), nullable=False),
        sa.Column("fecha_fin", sa.String(length=30), nullable=True),
        sa.Column("hora_desde", sa.String(length=10), nullable=False),
        sa.Column("hora_hasta", sa.String(length=10), nullable=False),
        sa.Column("duracion_minutos", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("presencial", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("virtual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dias_especiales_web_medico", "dias_especiales_web", ["medico"]
    )


def downgrade() -> None:
    op.drop_index("ix_dias_especiales_web_medico", table_name="dias_especiales_web")
    op.drop_table("dias_especiales_web")

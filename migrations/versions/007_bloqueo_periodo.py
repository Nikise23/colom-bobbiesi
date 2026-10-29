"""Revision ID: 007_bloqueo_periodo

Agrega fecha_fin para bloqueos web por período (fecha inicio → fecha fin).
"""

from alembic import op
import sqlalchemy as sa


revision = "007_bloqueo_periodo"
down_revision = "006_agenda_web"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bloqueos_web",
        sa.Column("fecha_fin", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bloqueos_web", "fecha_fin")

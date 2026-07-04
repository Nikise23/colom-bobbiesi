"""Ampliar columnas de fecha — algunos registros traen ISO con hora u otros formatos."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_widen_date_columns"
down_revision: Union[str, None] = "002_widen_dni_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "pacientes",
        "fecha_nacimiento",
        type_=sa.String(30),
        existing_type=sa.String(10),
    )
    op.alter_column(
        "turnos",
        "fecha",
        type_=sa.String(30),
        existing_type=sa.String(10),
    )
    op.alter_column(
        "historias_clinicas",
        "fecha_consulta",
        type_=sa.String(30),
        existing_type=sa.String(10),
    )
    op.alter_column(
        "pagos",
        "fecha",
        type_=sa.String(30),
        existing_type=sa.String(10),
    )


def downgrade() -> None:
    op.alter_column("pagos", "fecha", type_=sa.String(10), existing_type=sa.String(30))
    op.alter_column(
        "historias_clinicas",
        "fecha_consulta",
        type_=sa.String(10),
        existing_type=sa.String(30),
    )
    op.alter_column("turnos", "fecha", type_=sa.String(10), existing_type=sa.String(30))
    op.alter_column(
        "pacientes",
        "fecha_nacimiento",
        type_=sa.String(10),
        existing_type=sa.String(30),
    )

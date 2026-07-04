"""Ampliar columnas de hora — algunos horarios en /data superan 5 caracteres."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_widen_hora_columns"
down_revision: Union[str, None] = "003_widen_date_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "agenda_horarios",
        "hora",
        type_=sa.String(10),
        existing_type=sa.String(5),
    )
    op.alter_column(
        "turnos",
        "hora",
        type_=sa.String(10),
        existing_type=sa.String(5),
    )
    op.alter_column(
        "turnos",
        "hora_recepcion",
        type_=sa.String(10),
        existing_type=sa.String(5),
    )
    op.alter_column(
        "turnos",
        "hora_sala_espera",
        type_=sa.String(10),
        existing_type=sa.String(5),
    )
    op.alter_column(
        "pagos",
        "hora",
        type_=sa.String(10),
        existing_type=sa.String(5),
    )


def downgrade() -> None:
    op.alter_column("pagos", "hora", type_=sa.String(5), existing_type=sa.String(10))
    op.alter_column(
        "turnos",
        "hora_sala_espera",
        type_=sa.String(5),
        existing_type=sa.String(10),
    )
    op.alter_column(
        "turnos",
        "hora_recepcion",
        type_=sa.String(5),
        existing_type=sa.String(10),
    )
    op.alter_column("turnos", "hora", type_=sa.String(5), existing_type=sa.String(10))
    op.alter_column(
        "agenda_horarios",
        "hora",
        type_=sa.String(5),
        existing_type=sa.String(10),
    )

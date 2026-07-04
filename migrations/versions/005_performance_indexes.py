"""Revision ID: 005_performance_indexes

Índices en fechas para turnos y pagos.
"""

from alembic import op

revision = "005_performance_indexes"
down_revision = "004_widen_hora_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_turnos_fecha", "turnos", ["fecha"], unique=False)
    op.create_index("ix_pagos_fecha", "pagos", ["fecha"], unique=False)
    op.create_index("ix_turnos_estado", "turnos", ["estado"], unique=False)


def downgrade():
    op.drop_index("ix_turnos_estado", table_name="turnos")
    op.drop_index("ix_pagos_fecha", table_name="pagos")
    op.drop_index("ix_turnos_fecha", table_name="turnos")

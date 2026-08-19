"""add show_public to species and morphs (publicar/despublicar por taxon)

Revision ID: showpublictaxa01
Revises: checkoutat01
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'showpublictaxa01'
down_revision: Union[str, Sequence[str], None] = 'checkoutat01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('species', 'morphs'):
        op.add_column(
            table,
            sa.Column('show_public', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        )


def downgrade() -> None:
    for table in ('species', 'morphs'):
        op.drop_column(table, 'show_public')

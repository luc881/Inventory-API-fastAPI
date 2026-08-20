"""add image to species and morphs (foto del taxon para la tarjeta)

Revision ID: taxonimage01
Revises: showpublictaxa01
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'taxonimage01'
down_revision: Union[str, Sequence[str], None] = 'showpublictaxa01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('species', 'morphs'):
        op.add_column(table, sa.Column('image', sa.String(length=250), nullable=True))


def downgrade() -> None:
    for table in ('species', 'morphs'):
        op.drop_column(table, 'image')

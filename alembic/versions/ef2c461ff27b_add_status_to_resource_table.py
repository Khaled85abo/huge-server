"""Add status to resource table

Revision ID: ef2c461ff27b
Revises: 14bb851be813
Create Date: 2024-10-18 20:47:45.317557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef2c461ff27b'
down_revision: Union[str, None] = '14bb851be813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('resource', sa.Column('status', sa.Text(), nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('resource', 'status')
    # ### end Alembic commands ###

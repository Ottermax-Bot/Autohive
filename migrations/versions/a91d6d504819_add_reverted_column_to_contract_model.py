"""Add reverted column to Contract model

Revision ID: a91d6d504819
Revises: 6af4582d3287
Create Date: 2024-12-23 15:57:10.730320

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a91d6d504819'
down_revision = '6af4582d3287'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('contract', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reverted', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('contract', schema=None) as batch_op:
        batch_op.drop_column('reverted')

    # ### end Alembic commands ###
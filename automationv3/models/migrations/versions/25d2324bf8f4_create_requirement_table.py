"""create requirement table

Revision ID: 25d2324bf8f4
Revises: 
Create Date: 2023-06-25 22:21:45.016664

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '25d2324bf8f4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('Requirement',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('text', sa.String(length=1024), nullable=False),
    sa.Column('subsystem', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('Requirement')
    # ### end Alembic commands ###

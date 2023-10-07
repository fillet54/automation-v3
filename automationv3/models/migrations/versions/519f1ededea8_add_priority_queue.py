"""add priority queue

Revision ID: 519f1ededea8
Revises: 25d2324bf8f4
Create Date: 2023-10-05 22:58:45.687934

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '519f1ededea8'
down_revision = '25d2324bf8f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('Queue',
    sa.Column('message_id', sa.String(), nullable=False),
    sa.Column('message', sa.String(), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('in_time', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    sa.Column('lock_time', sa.DateTime(), nullable=True),
    sa.Column('done_time', sa.DateTime(), nullable=True),
    sa.Column('priority', sa.Integer(), server_default=sa.schema.DefaultClause("0")),
    sa.PrimaryKeyConstraint('message_id')
    )
    op.create_index('queue_status_idx', 'Queue', ['status'])

def downgrade() -> None:
    op.drop_table('Queue')

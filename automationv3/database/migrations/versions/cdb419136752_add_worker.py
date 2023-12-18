"""Add Worker

Revision ID: cdb419136752
Revises: 519f1ededea8
Create Date: 2023-11-13 21:57:10.997652

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "cdb419136752"
down_revision = "519f1ededea8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "Worker",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("status", sa.String(), default="available"),
        sa.Column(
            "last_keepalive",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("Worker")

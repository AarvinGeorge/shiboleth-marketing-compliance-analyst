# meta: alembic revision — additive retrieval_keywords on rules (customize
# scorecard layer; user-added rules need LLM-derived keyword families or
# retrieval has nothing to anchor on).
"""rules retrieval_keywords

Revision ID: 94a47fceda41
Revises: 4d5c89485181
Create Date: 2026-07-13 11:09:09.899882
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '94a47fceda41'
down_revision: Union[str, None] = '4d5c89485181'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy.dialects import postgresql
    op.add_column("rules", sa.Column(
        "retrieval_keywords", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("rules", "retrieval_keywords")

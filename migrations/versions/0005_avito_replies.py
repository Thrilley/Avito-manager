"""Persistent Avito conversations and review-only GPT drafts."""
from alembic import op
import sqlalchemy as sa
revision = '0005_avito_replies'
down_revision = '0004_telegram'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('avito_chat',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('source_account.id'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('human_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint('source_id', 'external_id', name='uq_avito_chat'))
    op.create_table('avito_message',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.Integer(), sa.ForeignKey('avito_chat.id'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('text', sa.String(4000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('chat_id', 'external_id', name='uq_avito_message'))
    op.create_table('avito_reply',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.Integer(), sa.ForeignKey('avito_chat.id'), nullable=False),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('avito_message.id'), nullable=False, unique=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('text', sa.String(2000)),
        sa.Column('error_code', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('uq_avito_generating', 'avito_reply', ['chat_id'], unique=True,
                    sqlite_where=sa.text("status = 'generating'"),
                    postgresql_where=sa.text("status = 'generating'"))

def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping conversations.')

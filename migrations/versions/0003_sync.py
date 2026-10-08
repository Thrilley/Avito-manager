"""Source accounts, synchronization journal and cached source snapshots."""
from alembic import op
import sqlalchemy as sa
revision = '0003_sync'
down_revision = '0002_users'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('external_listing', sa.Column('source_present', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('external_listing', sa.Column('source_data', sa.JSON()))
    op.create_table('source_account',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('platform', sa.String(30), nullable=False),
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.UniqueConstraint('platform', 'account_id', name='uq_source_account'))
    op.create_table('sync_run',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('source_account.id'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.String(50)),
        sa.Column('imported', sa.Integer(), nullable=False, server_default='0'))
    op.create_index('uq_running_sync', 'sync_run', ['source_id'], unique=True,
        sqlite_where=sa.text("status = 'running'"), postgresql_where=sa.text("status = 'running'"))

def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping synchronization data.')

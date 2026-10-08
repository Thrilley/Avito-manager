"""Users and private catalog ownership; preserve legacy records as unassigned."""
from alembic import op
import sqlalchemy as sa
revision = '0002_users'
down_revision = '0001_catalog'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(100), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(512), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    if op.get_bind().dialect.name == 'sqlite':
        # ADD COLUMN preserves external_listing foreign keys and existing rows.
        op.execute('ALTER TABLE listing ADD COLUMN owner_id INTEGER REFERENCES users(id)')
    else:
        op.add_column('listing', sa.Column('owner_id', sa.Integer()))
        op.create_foreign_key('fk_listing_owner', 'listing', 'users', ['owner_id'], ['id'])
    op.create_index('ix_listing_owner_id', 'listing', ['owner_id'])

def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping ownership data.')

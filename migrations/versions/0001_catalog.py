"""Create catalog or adopt the original SQLite listing table without dropping data."""
from alembic import op
import sqlalchemy as sa

revision = '0001_catalog'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    if 'listing' not in inspector.get_table_names():
        op.create_table('listing',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('description', sa.String(), nullable=False),
            sa.Column('price', sa.Numeric(12, 2), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('brand', sa.String(100)), sa.Column('size', sa.String(30)),
            sa.Column('condition', sa.String(30)),
            sa.Column('currency', sa.String(3), nullable=False, server_default='RUB'))
    else:
        # Fail rather than silently rewrite invalid legacy records.
        bad = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM listing WHERE title IS NULL OR trim(title) = '' OR description IS NULL OR price IS NULL OR price <= 0 OR created_at IS NULL OR status IS NULL")).scalar()
        if bad:
            raise RuntimeError('Legacy records require validation before migration; original records preserved.')
        with op.batch_alter_table('listing') as batch:
            batch.alter_column('title', existing_type=sa.String(), nullable=False)
            batch.alter_column('description', existing_type=sa.String(), nullable=False)
            batch.alter_column('price', existing_type=sa.Float(), type_=sa.Numeric(12, 2), nullable=False)
            batch.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), nullable=False)
            batch.alter_column('status', existing_type=sa.String(), nullable=False)
            batch.add_column(sa.Column('brand', sa.String(100)))
            batch.add_column(sa.Column('size', sa.String(30)))
            batch.add_column(sa.Column('condition', sa.String(30)))
            batch.add_column(sa.Column('currency', sa.String(3), nullable=False, server_default='RUB'))
    op.create_table('external_listing',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('listing_id', sa.Integer(), sa.ForeignKey('listing.id', ondelete='CASCADE'), nullable=False),
        sa.Column('platform', sa.String(30), nullable=False),
        sa.Column('account_id', sa.String(100), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('url', sa.String(2048)), sa.Column('external_status', sa.String(100)),
        sa.Column('synced_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('platform', 'account_id', 'external_id', name='uq_external_identity'))
    op.create_index('ix_external_listing_listing_id', 'external_listing', ['listing_id'])

def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead.')

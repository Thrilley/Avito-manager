"""Single-use Telegram links and private owner bindings."""
from alembic import op
import sqlalchemy as sa
revision = '0004_telegram'
down_revision = '0003_sync'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('telegram_link_code',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('code_hash',sa.String(64),nullable=False,unique=True),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('used_at',sa.DateTime(timezone=True)))
    op.create_table('telegram_binding',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('telegram_id',sa.BigInteger(),nullable=False,unique=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,unique=True))

def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping Telegram bindings.')

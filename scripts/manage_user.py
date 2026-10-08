"""Local administrator/ownership management. Never grants roles via public registration."""
import argparse
from getpass import getpass
from sqlalchemy import select, update
from app.database import SessionLocal
from app.models import User, Listing
from app.core.security import hasher

parser = argparse.ArgumentParser()
parser.add_argument('username')
parser.add_argument('--admin', action='store_true')
parser.add_argument('--claim-legacy', action='store_true', help='Assign only unowned listings')
args = parser.parse_args()
username = args.username.lower()
import re
if not re.fullmatch(r'[a-z0-9_.-]{3,100}', username):
    parser.error('Username must match API rules')
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        password = getpass('New password (12–128 characters): ')
        if not 12 <= len(password) <= 128 or password != getpass('Repeat password: '):
            parser.error('Invalid or mismatching password')
        user = User(username=username, password_hash=hasher.hash(password))
        db.add(user)
        db.flush()
    if args.admin:
        user.is_admin = True
    count = 0
    if args.claim_legacy:
        count = db.execute(update(Listing).where(Listing.owner_id.is_(None)).values(owner_id=user.id)).rowcount
    db.commit()
    print(f'User configured; legacy listings assigned: {count}')

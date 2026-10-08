"""Integration check for an EMPTY disposable PostgreSQL DB only."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from sqlalchemy import select, text, create_engine
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models import User, Listing, TelegramBinding, SourceAccount, ExternalListing
from app.core.security import hasher
from app.services.telegram_service import catalog_page, CatalogFilter
from scripts.transfer_sqlite import transfer, TransferError

if os.getenv('ALLOW_DISPOSABLE_POSTGRES_TEST') != 'yes' or engine.dialect.name != 'postgresql':
    raise SystemExit('Requires an explicitly disposable PostgreSQL test database')
with engine.connect() as db:
    if db.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")).scalar():
        raise SystemExit('Test database must initially be empty')
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True)
subprocess.run([sys.executable,'-m','alembic','check'],check=True)
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'source.db'
    env=dict(os.environ,DATABASE_URL=f'sqlite:///{path}')
    env.pop('DATABASE_HOST',None)
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True)
    source=create_engine(f'sqlite:///{path}')
    try:
        with Session(source) as db:
            user=User(id=20,username='integration',password_hash=hasher.hash('integration-password-only'))
            db.add(user)
            db.flush()
            listing=Listing(id=40,owner_id=20,title='Nike',description='Integration test',price='100.25',status='active',brand='Nike',size='42')
            db.add(listing)
            db.flush()
            account=SourceAccount(id=60,owner_id=20,platform='test',account_id='123')
            db.add(account)
            db.flush()
            db.add_all([TelegramBinding(telegram_id=9876543210,owner_id=20),ExternalListing(listing_id=40,platform='test',account_id='123',external_id='42',source_data={'catalog_status':'active','price':'100.25'})])
            db.commit()
        counts=transfer(path,engine)
        with SessionLocal() as db:
            assert db.scalar(select(User)) is None
        counts=transfer(path,engine,apply=True)
        with SessionLocal() as db:
            assert db.get(Listing,40).owner_id==20
            rows,_=catalog_page(db,9876543210,CatalogFilter(brand='Nike',size='42'))
            assert len(rows)==1 and rows[0]['price']=='100.25'
            listing=Listing(owner_id=20,title='Next',description='',price=50,status='active')
            user=User(username='next',password_hash='test')
            db.add_all([listing,user])
            db.commit()
            assert listing.id>40 and user.id>20
        try:
            transfer(path,engine,apply=True)
        except TransferError:
            pass
        else:
            raise AssertionError('Nonempty PostgreSQL target was not rejected')
        from fastapi.testclient import TestClient
        from app.legacy_app import app
        with TestClient(app) as client:
            assert client.get('/health/ready').status_code==200
            assert client.get('/api/v1/listings').status_code==401
            response=client.post('/api/v1/auth/login',json={'username':'integration','password':'integration-password-only'})
            assert response.status_code==200
            token=response.json()['access_token']
            response=client.get('/api/v1/listings',headers={'Authorization':'Bearer '+token})
            assert response.status_code==200 and len(response.json())==2
        from main import app as autoreply_app
        with TestClient(autoreply_app) as client:
            assert client.get('/health/ready').status_code == 200
            assert client.get('/api/v1/avito/chats').status_code == 401
            assert client.get('/api/v1/listings').status_code == 404
            assert client.get('/api/v1/avito/chats', headers={'Authorization': 'Bearer '+token}).status_code == 200
        print('PostgreSQL migrations, dry run, committed transfer, IDs, JWT and bot catalog passed')
    finally:
        source.dispose()

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url, URL
from sqlalchemy.orm import sessionmaker, declarative_base

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "database.db"}')
if os.getenv('DATABASE_HOST'):
    url = URL.create('postgresql+psycopg', username=os.getenv('DATABASE_USER','avito'),
                     password=os.environ['DATABASE_PASSWORD'], host=os.environ['DATABASE_HOST'],
                     port=int(os.getenv('DATABASE_PORT','5432')), database=os.getenv('DATABASE_NAME','avito_manager'))
else:
    url = make_url(DATABASE_URL)
if url.drivername in ('postgres', 'postgresql'):
    url = url.set(drivername='postgresql+psycopg')
engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, connect_args={'check_same_thread': False} if url.get_backend_name() == 'sqlite' else {})
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

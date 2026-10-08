from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from app.database import engine
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.database import ROOT

router=APIRouter(tags=['health'])

@router.get('/health/live')
def live():
    return {'status':'ok'}

@router.get('/health/ready')
def ready():
    try:
        config=Config(str(ROOT/'alembic.ini'))
        config.set_main_option('script_location',str(ROOT/'migrations'))
        heads=set(ScriptDirectory.from_config(config).get_heads())
        with engine.connect() as connection:
            versions=set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
        if versions!=heads:
            raise RuntimeError('Database migrations required')
    except Exception:
        raise HTTPException(503,'Database unavailable or migration required')
    return {'status':'ready'}

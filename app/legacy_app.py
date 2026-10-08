from fastapi import FastAPI
from app.routers.listing import router as listing_router
from app.routers.catalog import router as catalog_router

app = FastAPI(title='Avito Manager', version='0.2.0')
app.include_router(listing_router)
app.include_router(catalog_router)

from app.routers.auth import router as auth_router
app.include_router(auth_router)

from app.routers.sources import router as sources_router
app.include_router(sources_router)

from app.routers.telegram import router as telegram_router
app.include_router(telegram_router)

from app.routers.health import router as health_router
app.include_router(health_router)

from app.routers.avito import router as avito_router
app.include_router(avito_router)

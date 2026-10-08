"""Avito auto-replier: conversations, operator handoff and access control only."""
from fastapi import FastAPI
from app.routers.auth import router as auth_router
from app.routers.avito import router as avito_router
from app.routers.health import router as health_router

app = FastAPI(title='Автоответчик Авито', version='0.3.0')
app.include_router(auth_router)
app.include_router(avito_router)
app.include_router(health_router)

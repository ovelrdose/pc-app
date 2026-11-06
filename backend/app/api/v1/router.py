"""Корневой роутер `/api/v1`."""

from fastapi import APIRouter

from app.api.v1 import auth, builds, catalog, consultations, health, me, sessions
from app.api.v1.admin.router import admin_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(me.router)
api_router.include_router(consultations.router)
api_router.include_router(builds.router)
api_router.include_router(admin_router)

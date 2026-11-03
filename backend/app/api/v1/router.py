"""Корневой роутер `/api/v1`."""

from fastapi import APIRouter

from app.api.v1 import builds, catalog, consultations, health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(consultations.router)
api_router.include_router(builds.router)

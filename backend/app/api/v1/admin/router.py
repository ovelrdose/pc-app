"""Админские роутеры этапа 9 (ADR 0010): каталог, база знаний, пользователи."""

from fastapi import APIRouter

from app.api.v1.admin import catalog, components, kb, reference, rules, users

admin_router = APIRouter()
admin_router.include_router(components.router)
admin_router.include_router(catalog.router)
admin_router.include_router(rules.router)
admin_router.include_router(kb.router)
admin_router.include_router(reference.router)
admin_router.include_router(users.router)

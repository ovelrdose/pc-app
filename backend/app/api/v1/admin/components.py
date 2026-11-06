"""Админка каталога: CRUD компонентов (ADR 0010 п.7–8). Удаления нет — только `inactive`."""

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CacheDep, SessionDep
from app.api.v1.admin.deps import CatalogAdminOwner, actor
from app.expert.frames import Category, ComponentFrame, ComponentStatus
from app.models.component import ComponentSource
from app.schemas.admin import ComponentPatchIn
from app.schemas.catalog import ComponentOut, ComponentPage, ComponentQuery
from app.services.catalog_admin import CatalogAdminService

router = APIRouter(prefix="/admin/components", tags=["admin-catalog"])


@router.get("", summary="Каталог: список с фильтрами (включая снятые с продажи)")
async def list_components(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogAdminOwner,
    category: Category | None = None,
    brand: Annotated[str | None, Query(max_length=64)] = None,
    status: ComponentStatus | None = None,
    source: ComponentSource | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Поиск по названию и SKU")] = None,
    in_stock: bool | None = None,
    price_stale_days: Annotated[
        int | None, Query(ge=1, description="Цена не проверялась больше N дней")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ComponentPage:
    service = CatalogAdminService(session, cache)
    query = ComponentQuery(
        category=category,
        brand=brand,
        search=q,
        in_stock=in_stock,
        include_inactive=True,
        status=status,
        source=source,
        price_checked_before=(
            date.today() - timedelta(days=price_stale_days) if price_stale_days else None
        ),
    )
    return await service.list_components(query, limit=limit, offset=offset)


@router.post("", status_code=201, summary="Каталог: создать компонент из JSON фрейма категории")
async def create_component(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogAdminOwner,
    frame: ComponentFrame,
) -> ComponentOut:
    return await CatalogAdminService(session, cache).create_component(frame, author=actor(owner))


@router.get("/{component_id}", summary="Каталог: карточка компонента")
async def get_component(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogAdminOwner,
    component_id: uuid.UUID,
) -> ComponentOut:
    return await CatalogAdminService(session, cache).get_component(component_id)


@router.put("/{component_id}", summary="Каталог: полная замена компонента фреймом")
async def replace_component(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogAdminOwner,
    component_id: uuid.UUID,
    frame: ComponentFrame,
) -> ComponentOut:
    return await CatalogAdminService(session, cache).replace_component(
        component_id, frame, author=actor(owner)
    )


@router.patch("/{component_id}", summary="Каталог: служебные поля (наличие, статус продажи)")
async def patch_component(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogAdminOwner,
    component_id: uuid.UUID,
    patch: ComponentPatchIn,
) -> ComponentOut:
    return await CatalogAdminService(session, cache).patch_component(
        component_id,
        in_stock=patch.in_stock,
        status=patch.status,
        author=actor(owner),
    )

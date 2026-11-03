"""Публичный каталог комплектующих и схемы фреймов."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.expert.frames import Category
from app.schemas.catalog import ComponentOut, ComponentPage, ComponentQuery, FrameOut
from app.services.catalog import CatalogService, list_frames

router = APIRouter(tags=["catalog"])


@router.get("/components", summary="Каталог комплектующих с фильтрами")
async def list_components(
    session: SessionDep,
    category: Category | None = None,
    brand: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=100, description="Поиск по названию и SKU")] = None,
    in_stock: bool | None = None,
    min_price_kop: Annotated[int | None, Query(ge=0)] = None,
    max_price_kop: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ComponentPage:
    query = ComponentQuery(
        category=category,
        brand=brand,
        search=q,
        in_stock=in_stock,
        min_price_kop=min_price_kop,
        max_price_kop=max_price_kop,
    )
    return await CatalogService(session).list_components(query, limit=limit, offset=offset)


@router.get("/components/{component_id}", summary="Карточка компонента")
async def get_component(component_id: uuid.UUID, session: SessionDep) -> ComponentOut:
    return await CatalogService(session).get_component(component_id)


@router.get("/frames", summary="Схемы фреймов категорий")
async def get_frames() -> list[FrameOut]:
    return list_frames()

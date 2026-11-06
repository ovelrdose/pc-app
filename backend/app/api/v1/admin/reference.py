"""Админка базы знаний: справочники, анкета, golden cases и регенерация правил."""

from typing import Any

from fastapi import APIRouter, Body, Query

from app.api.deps import CacheDep, SessionDep
from app.api.v1.admin.deps import KnowledgeOwner, actor
from app.schemas.admin import RegenerateOut
from app.services.knowledge_admin import KnowledgeAdminService

router = APIRouter(prefix="/admin/reference", tags=["admin-kb"])


@router.get("", summary="Все справочники, анкета и golden cases рабочей копии")
async def list_reference(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
) -> dict[str, Any]:
    return await KnowledgeAdminService(session, cache).reference()


@router.get("/{name}", summary="Один справочник, анкета или golden cases")
async def get_reference(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    name: str,
) -> dict[str, Any]:
    return await KnowledgeAdminService(session, cache).reference(name)


@router.put("/{name}", summary="Заменить справочник целиком (валидация схемами ядра)")
async def replace_reference(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    name: str,
    data: Any = Body(...),  # noqa: ANN401, B008 — тело запроса целиком; схема проверяется в сервисе
) -> dict[str, Any]:
    return await KnowledgeAdminService(session, cache).replace_reference(name, data)


@router.post("/regenerate", summary="Перегенерировать табличные правила в черновик (diff)")
async def regenerate_reference(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    dry_run: bool = Query(default=True, description="Только diff-отчёт, без записи"),
) -> RegenerateOut:
    report = await KnowledgeAdminService(session, cache).regenerate(
        dry_run=dry_run, author=actor(owner)
    )
    return RegenerateOut(
        dry_run=report.dry_run,
        created=list(report.created),
        updated=list(report.updated),
        removed=list(report.removed),
        overrides=list(report.overrides),
    )

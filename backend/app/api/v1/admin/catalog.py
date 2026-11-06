"""Админка каталога: импорт CSV с журналом, экспорт zip, позиции, требующие внимания."""

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile

from app.api.deps import CacheDep, SessionDep, SettingsDep
from app.api.v1.admin.deps import CatalogAdminOwner, CatalogIssuesOwner, actor
from app.expert.frames import Category, ComponentStatus
from app.schemas.admin import CatalogImportOut
from app.schemas.catalog import ComponentPage, ComponentQuery
from app.services.catalog_admin import CatalogAdminService

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"])


@router.post(
    "/import", status_code=201, summary="Импорт CSV одной категории (dry-run или применение)"
)
async def import_catalog(
    session: SessionDep,
    cache: CacheDep,
    settings: SettingsDep,
    owner: CatalogAdminOwner,
    category: Annotated[Category, Query(description="Категория из имени файла каталога")],
    dry_run: bool = Query(default=False, description="Только отчёт, без изменения БД"),
    upload: UploadFile = File(description="CSV файл одной категории (≤ 2 МБ)"),  # noqa: B008
) -> CatalogImportOut:
    content = await upload.read()
    report = await CatalogAdminService(session, cache).import_csv(
        filename=upload.filename or "import.csv",
        content=content,
        category=category,
        dry_run=dry_run,
        max_bytes=settings.catalog_import_max_bytes,
        author=actor(owner),
    )
    return CatalogImportOut(
        import_id=report.import_id,
        status=report.status.value,
        dry_run=report.dry_run,
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        catalog_revision=report.catalog_revision,
        status_counts=report.status_counts,
        errors=list(report.errors),
        warnings=list(report.warnings),
    )


@router.get("/export", summary="Экспорт каталога: zip с <category>.csv в формате §12")
async def export_catalog(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogAdminOwner,
) -> Response:
    payload = await CatalogAdminService(session, cache).export_zip()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="catalog-export.zip"'},
    )


@router.get("/issues", summary="Позиции со статусами incomplete/needs_kb и причинами")
async def catalog_issues(
    session: SessionDep,
    cache: CacheDep,
    owner: CatalogIssuesOwner,
    category: Annotated[Category | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ComponentPage:
    service = CatalogAdminService(session, cache)
    query = ComponentQuery(
        category=category,
        search=q,
        statuses=(ComponentStatus.INCOMPLETE, ComponentStatus.NEEDS_KB),
    )
    return await service.list_components(query, limit=limit, offset=offset)

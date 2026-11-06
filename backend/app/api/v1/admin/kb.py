"""Админка базы знаний: валидация, публикация, снимки, экспорт, словарь фактов."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CacheDep, SessionDep
from app.api.v1.admin.deps import KnowledgeOwner, actor
from app.expert.vocabulary import all_specs
from app.schemas.admin import (
    GoldenReportOut,
    KbStatusOut,
    PublishOut,
    SnapshotOut,
    ValidateReportOut,
    VocabularyOut,
)
from app.services.knowledge_admin import KnowledgeAdminService

router = APIRouter(prefix="/admin/kb", tags=["admin-kb"])


@router.get("/vocabulary", summary="Словарь фактов для конструктора условий")
async def vocabulary(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
) -> list[VocabularyOut]:
    return [
        VocabularyOut(
            path=spec.path,
            type=spec.type.value,
            role=spec.role.value,
            title=spec.title,
            values=list(spec.values),
        )
        for spec in all_specs()
    ]


@router.get("/status", summary="Лёгкий статус черновика: checksum, совпадение со снимком, правил")
async def kb_status(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
) -> KbStatusOut:
    status = await KnowledgeAdminService(session, cache).status()
    return KbStatusOut(
        checksum=status.checksum,
        matches_latest=status.matches_latest,
        rules_total=status.rules_total,
    )


@router.post("/validate", summary="Stateless-валидация черновика (§6.2 + golden), без записи")
async def validate_kb(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
) -> ValidateReportOut:
    report = await KnowledgeAdminService(session, cache).validate()
    return ValidateReportOut(
        rules_total=report.rules_total,
        errors=list(report.errors),
        warnings=list(report.warnings),
        golden=GoldenReportOut(
            passed=report.golden.passed,
            failed=report.golden.failed,
            failures=report.golden.failures,
        ),
        checksum=report.checksum,
        matches_latest=report.matches_latest,
    )


@router.post("/publish", summary="Опубликовать черновик (при ошибках 409, снимок не создаётся)")
async def publish_kb(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    comment: Annotated[str | None, Query(max_length=500)] = None,
) -> PublishOut:
    report = await KnowledgeAdminService(session, cache).publish(
        comment=comment, author=actor(owner)
    )
    return PublishOut(
        snapshot_id=report.snapshot_id,
        version=report.version,
        created=report.created,
        rules=report.rules,
        warnings=report.warnings,
        golden_cases=report.golden_cases,
        statuses_changed=report.statuses_changed,
    )


@router.get("/snapshots", summary="Опубликованные снимки базы знаний, новые первыми")
async def list_snapshots(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
) -> list[SnapshotOut]:
    snapshots = await KnowledgeAdminService(session, cache).snapshots()
    return [SnapshotOut.model_validate(item) for item in snapshots]


@router.post("/snapshots/{snapshot_id}/republish", summary="Откат: повторная публикация снимка")
async def republish_snapshot(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    snapshot_id: int,
) -> PublishOut:
    report = await KnowledgeAdminService(session, cache).republish(
        snapshot_id=snapshot_id, author=actor(owner)
    )
    return PublishOut(
        snapshot_id=report.snapshot_id,
        version=report.version,
        created=report.created,
        rules=report.rules,
        warnings=report.warnings,
        golden_cases=report.golden_cases,
        statuses_changed=report.statuses_changed,
    )


@router.get("/export", summary="Экспорт БЗ: zip с деревом как в knowledge/ (round-trip)")
async def export_kb(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
) -> Response:
    payload = await KnowledgeAdminService(session, cache).export_zip()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="knowledge-export.zip"'},
    )

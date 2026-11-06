"""Админка базы знаний: CRUD правил и изолированный тест прямого вывода (ADR 0010 п.4, п.7)."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CacheDep, SessionDep
from app.api.v1.admin.deps import KnowledgeOwner, actor
from app.expert.dsl.schema import Rule, RuleKind, RuleOrigin
from app.schemas.admin import (
    RuleDetailOut,
    RuleOut,
    RulePage,
    RuleTestActionOut,
    RuleTestFactOut,
    RuleTestIn,
    RuleTestOut,
)
from app.services.knowledge_admin import KnowledgeAdminService

router = APIRouter(prefix="/admin/rules", tags=["admin-kb"])


@router.get("", summary="Правила рабочей копии: список с фильтрами")
async def list_rules(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    group: Annotated[str | None, Query(max_length=32)] = None,
    kind: RuleKind | None = None,
    origin: RuleOrigin | None = None,
    enabled: bool | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Поиск по коду и названию")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RulePage:
    items, total = await KnowledgeAdminService(session, cache).list_rules(
        group=group,
        kind=kind,
        origin=origin,
        enabled=enabled,
        search=q,
        limit=limit,
        offset=offset,
    )
    return RulePage(
        items=[RuleOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201, summary="Создать ручное правило (код PREFIX-NNN уникален)")
async def create_rule(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    rule: Rule,
) -> RuleOut:
    result = await KnowledgeAdminService(session, cache).create_rule(rule, author=actor(owner))
    return RuleOut.model_validate(result)


@router.get("/{code}", summary="Правило с историей ревизий")
async def get_rule(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    code: str,
) -> RuleDetailOut:
    detail = await KnowledgeAdminService(session, cache).rule_detail(code)
    return RuleDetailOut(
        rule=RuleOut.model_validate(detail["rule"]),
        revisions=detail["revisions"],
    )


@router.put("/{code}", summary="Полная замена правила (новая ревизия)")
async def replace_rule(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    code: str,
    rule: Rule,
) -> RuleOut:
    result = await KnowledgeAdminService(session, cache).replace_rule(
        code, rule, author=actor(owner)
    )
    return RuleOut.model_validate(result)


@router.post("/{code}/retire", summary="Вывести правило из базы (enabled=false, новая ревизия)")
async def retire_rule(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    code: str,
) -> RuleOut:
    result = await KnowledgeAdminService(session, cache).retire_rule(code, author=actor(owner))
    return RuleOut.model_validate(result)


@router.post("/{code}/test", summary="Изолированный прямой вывод на заданных фактах")
async def test_rule(
    session: SessionDep,
    cache: CacheDep,
    owner: KnowledgeOwner,
    code: str,
    payload: RuleTestIn,
) -> RuleTestOut:
    result = await KnowledgeAdminService(session, cache).test_rule(code, payload.facts)
    return RuleTestOut(
        matched=result.matched,
        premise_cf=result.premise_cf,
        actions=[RuleTestActionOut(**asdict(action)) for action in result.actions],
        facts_after=[RuleTestFactOut(**asdict(fact)) for fact in result.facts_after],
        failures=list(result.failures),
    )

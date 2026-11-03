"""Сборки: карточка, объяснения, «почему не», замены, гипотезы, правки, сравнение, PDF."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CacheDep, SessionDep
from app.expert.frames import Category
from app.schemas.consultations import (
    AlternativeOut,
    BuildDetail,
    BuildPatch,
    CompareOut,
    CompareRequest,
    ExplanationOut,
    HypothesisOut,
    HypothesisRequest,
    ModificationOut,
    ModificationRequest,
    WhyNotOut,
)
from app.services.builds import BuildService
from app.services.pdf import render_pdf

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("/{build_id}", summary="Сборка, прогноз и замечания")
async def get_build(build_id: uuid.UUID, session: SessionDep, cache: CacheDep) -> BuildDetail:
    return await BuildService(session, cache).detail(build_id)


@router.patch("/{build_id}", summary="Сохранить или переименовать сборку")
async def patch_build(
    build_id: uuid.UUID, data: BuildPatch, session: SessionDep, cache: CacheDep
) -> BuildDetail:
    return await BuildService(session, cache).patch(build_id, data)


@router.get("/{build_id}/explanation", summary="Почему эта сборка: рассуждение и полезность")
async def get_explanation(
    build_id: uuid.UUID, session: SessionDep, cache: CacheDep
) -> ExplanationOut:
    return await BuildService(session, cache).explanation(build_id)


@router.get("/{build_id}/why-not", summary="Почему не этот товар")
async def get_why_not(
    build_id: uuid.UUID, component_id: uuid.UUID, session: SessionDep, cache: CacheDep
) -> WhyNotOut:
    return await BuildService(session, cache).why_not(build_id, component_id)


@router.get("/{build_id}/alternatives", summary="Совместимые замены детали")
async def get_alternatives(
    build_id: uuid.UUID, category: Category, session: SessionDep, cache: CacheDep
) -> list[AlternativeOut]:
    return await BuildService(session, cache).alternatives(build_id, category)


@router.post("/{build_id}/hypotheses", summary="Потянет ли: обратный вывод")
async def post_hypothesis(
    build_id: uuid.UUID, data: HypothesisRequest, session: SessionDep, cache: CacheDep
) -> HypothesisOut:
    return await BuildService(session, cache).hypothesis(build_id, data)


@router.post(
    "/{build_id}/modifications",
    status_code=status.HTTP_201_CREATED,
    summary="Правка: новая сборка и разница",
)
async def post_modification(
    build_id: uuid.UUID, data: ModificationRequest, session: SessionDep, cache: CacheDep
) -> ModificationOut:
    return await BuildService(session, cache).modify(build_id, data)


@router.post("/compare", summary="Сравнение 2–3 сборок")
async def post_compare(data: CompareRequest, session: SessionDep, cache: CacheDep) -> CompareOut:
    return await BuildService(session, cache).compare(data.build_ids)


@router.get(
    "/{build_id}/pdf",
    summary="PDF: спецификация, обоснование, прогноз",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_pdf(build_id: uuid.UUID, session: SessionDep, cache: CacheDep) -> Response:
    context = await BuildService(session, cache).pdf_context(build_id)
    pdf = render_pdf(context["build"], context["reasoning"])
    filename = f"sborshik-{build_id}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

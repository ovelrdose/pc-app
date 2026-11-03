"""Анкета, консультации и разбор невыполнимых запросов."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CacheDep, SessionDep
from app.schemas.consultations import (
    ConsultationCreate,
    ConsultationOut,
    GoalOut,
    InfeasibleOut,
    QuestionnaireOut,
)
from app.services.consultations import ConsultationService

router = APIRouter(tags=["consultations"])


@router.get("/questionnaire", summary="Вопросы визарда")
async def get_questionnaire(session: SessionDep, cache: CacheDep) -> QuestionnaireOut:
    return await ConsultationService(session, cache).questionnaire()


@router.get("/goals", summary="Гипотезы, которые можно проверить («потянет ли»)")
async def get_goals(session: SessionDep, cache: CacheDep) -> list[GoalOut]:
    return await ConsultationService(session, cache).goals()


@router.post("/consultations", status_code=status.HTTP_201_CREATED, summary="Создать консультацию")
async def create_consultation(
    data: ConsultationCreate, session: SessionDep, cache: CacheDep
) -> ConsultationOut:
    return await ConsultationService(session, cache).create(data)


@router.get("/consultations/{consultation_id}", summary="Консультация и её сборки")
async def get_consultation(
    consultation_id: uuid.UUID, session: SessionDep, cache: CacheDep
) -> ConsultationOut:
    return await ConsultationService(session, cache).get(consultation_id)


@router.post(
    "/consultations/{consultation_id}/builds",
    status_code=status.HTTP_201_CREATED,
    summary="Запустить подбор: три варианта",
)
async def run_consultation(
    consultation_id: uuid.UUID, session: SessionDep, cache: CacheDep
) -> ConsultationOut:
    return await ConsultationService(session, cache).run(consultation_id)


@router.get(
    "/consultations/{consultation_id}/infeasible",
    summary="Почему ничего не подобралось: что мешает, как ослабить, что можно собрать",
)
async def get_infeasible(
    consultation_id: uuid.UUID, session: SessionDep, cache: CacheDep
) -> InfeasibleOut:
    return await ConsultationService(session, cache).infeasible(consultation_id)

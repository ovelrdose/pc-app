"""Схемы ответов проверок живости."""

from typing import Literal

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Ответ `/healthz` и `/readyz`."""

    status: Literal["ok"]

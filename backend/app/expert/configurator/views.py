"""Представления фактов для этапов подбора."""

from dataclasses import dataclass

from app.expert.configurator.plan import MANDATORY_CF
from app.expert.facts import Fact, FactView


@dataclass(frozen=True, slots=True)
class MandatoryView:
    """Скрывает желательные требования (`req.*` с CF < 0.5): фильтры видят только обязательные."""

    base: FactView

    def lookup(self, path: str) -> Fact | None:
        """Факт, если он не является желательным требованием."""
        fact = self.base.lookup(path)
        if fact is not None and path.startswith("req.") and fact.cf < MANDATORY_CF:
            return None
        return fact

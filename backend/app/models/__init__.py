"""ORM-модели. Каждая модель импортируется здесь, чтобы Alembic видел её в метаданных."""

from app.core.db import Base
from app.models.component import ComponentRow, ComponentSource
from app.models.consultation import BuildItemRow, BuildRow, ConsultationRow
from app.models.knowledge import KbSnapshotRow, ReferenceTableRow, RuleRevisionRow, RuleRow
from app.models.meta import MetaRow

__all__ = [
    "Base",
    "BuildItemRow",
    "BuildRow",
    "ComponentRow",
    "ComponentSource",
    "ConsultationRow",
    "KbSnapshotRow",
    "MetaRow",
    "ReferenceTableRow",
    "RuleRevisionRow",
    "RuleRow",
]

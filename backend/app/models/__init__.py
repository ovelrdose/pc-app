"""ORM-модели. Каждая модель импортируется здесь, чтобы Alembic видел её в метаданных."""

from app.core.db import Base
from app.models.catalog_import import CatalogImportRow, CatalogImportStatus
from app.models.component import ComponentRow, ComponentSource
from app.models.consultation import BuildItemRow, BuildRow, ConsultationRow
from app.models.knowledge import KbSnapshotRow, ReferenceTableRow, RuleRevisionRow, RuleRow
from app.models.meta import MetaRow
from app.models.user import GuestSessionRow, RefreshTokenRow, UserRole, UserRow

__all__ = [
    "Base",
    "BuildItemRow",
    "BuildRow",
    "CatalogImportRow",
    "CatalogImportStatus",
    "ComponentRow",
    "ComponentSource",
    "ConsultationRow",
    "GuestSessionRow",
    "KbSnapshotRow",
    "MetaRow",
    "ReferenceTableRow",
    "RefreshTokenRow",
    "RuleRevisionRow",
    "RuleRow",
    "UserRole",
    "UserRow",
]

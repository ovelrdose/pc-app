"""Проверка владельца консультации или сборки.

Владелец — аккаунт, создавший консультацию, либо гостевая сессия, если входа
не было. Консультации без владельца (созданные до этапа 8) недоступны никому.
"""

from dataclasses import dataclass

from app.core.errors import NotFoundError
from app.models import ConsultationRow, GuestSessionRow, UserRow


@dataclass(frozen=True)
class OwnerContext:
    """Кто обращается к API: аккаунт (приоритет) или гостевая сессия."""

    user: UserRow | None = None
    guest: GuestSessionRow | None = None


def owns_consultation(row: ConsultationRow, owner: OwnerContext) -> bool:
    """True, если консультация принадлежит текущему владельцу."""
    if row.user_id is not None:
        return owner.user is not None and row.user_id == owner.user.id
    if row.guest_session_id is not None:
        return owner.guest is not None and row.guest_session_id == owner.guest.id
    return False


def ensure_consultation_owner(row: ConsultationRow, owner: OwnerContext) -> None:
    """Бросает NotFoundError, если консультация не принадлежит владельцу.

    Чужой объект называем «не найденным», чтобы не раскрывать идентификаторы.
    """
    if not owns_consultation(row, owner):
        raise NotFoundError("Консультация не найдена", consultation_id=str(row.id))

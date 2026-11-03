"""Служебные значения приложения «ключ → значение» (например, ревизия каталога)."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MetaRow(Base):
    """Пара «ключ → значение»."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

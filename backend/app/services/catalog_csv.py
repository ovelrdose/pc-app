"""Чтение каталога из CSV: строка файла → фрейм категории (формат — knowledge/catalog/README.md)."""

import csv
import io
import types
import typing
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.expert.frames import FRAMES_BY_CATEGORY, Category, Component
from app.services.validation_messages import describe_validation_error

LIST_SEPARATOR = "|"
PRICE_COLUMNS = ("price_rub", "price_checked_at", "price_note")
MAX_PRICE_NOTE = 200


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    """Позиция каталога: фрейм и сведения о цене."""

    frame: Component
    price_checked_at: date | None
    price_note: str | None


@dataclass(frozen=True, slots=True)
class RowError:
    """Ошибка в строке файла (номер строки считается с заголовком, как в редакторе).

    `line` равен `None`, если ошибка относится к файлу целиком.
    """

    line: int | None
    messages: tuple[str, ...]

    def __str__(self) -> str:
        text = "; ".join(self.messages)
        return f"строка {self.line}: {text}" if self.line is not None else text


@dataclass(slots=True)
class CatalogParseResult:
    """Результат разбора файла: принятые записи и ошибки."""

    records: list[CatalogRecord] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    fatal: bool = False
    """Файл отклонён целиком (не подходит заголовок): записей нет, импорт невозможен."""


def _is_list_slot(annotation: object) -> bool:
    origin = typing.get_origin(annotation)
    if origin is list:
        return True
    if origin in (typing.Union, types.UnionType):
        return any(_is_list_slot(arg) for arg in typing.get_args(annotation))
    return False


def _is_int_literal_slot(annotation: object) -> bool:
    # Literal[120, 140, ...] не приводит строку «120» к числу, поэтому такие слоты
    # (в том числе списки из них) конвертируются при разборе CSV.
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return all(isinstance(arg, int) for arg in typing.get_args(annotation))
    if origin in (list, typing.Union, types.UnionType):
        return any(_is_int_literal_slot(arg) for arg in typing.get_args(annotation))
    return False


def _to_int_if_digits(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def csv_columns(category: Category) -> list[str]:
    """Колонки CSV-шаблона категории: слоты фрейма (без цены в копейках) и сведения о цене."""
    frame = FRAMES_BY_CATEGORY[category]
    slots = [name for name in frame.model_fields if name not in ("category", "price_kop")]
    return [*slots, *PRICE_COLUMNS]


def _parse_price(raw: str) -> tuple[int | None, list[str]]:
    value = raw.replace(" ", "").replace(" ", "")
    if not value:
        return None, ["«Цена, ₽» (price_rub): не заполнено"]
    if not value.isdigit() or int(value) <= 0:
        return None, [f"«Цена, ₽» (price_rub) = «{raw}»: ожидается целое число рублей больше 0"]
    return int(value) * 100, []


def _parse_date(raw: str) -> tuple[date | None, list[str]]:
    if not raw:
        return None, []
    try:
        return date.fromisoformat(raw), []
    except ValueError:
        return None, [f"«Дата проверки цены» (price_checked_at) = «{raw}»: ожидается ГГГГ-ММ-ДД"]


def _parse_row(
    row: dict[str, str],
    frame_cls: type[Component],
    list_slots: frozenset[str],
    int_literal_slots: frozenset[str],
) -> tuple[CatalogRecord | None, list[str]]:
    price_kop, errors = _parse_price(row.get("price_rub", ""))
    checked_at, date_errors = _parse_date(row.get("price_checked_at", ""))
    errors += date_errors
    note = row.get("price_note") or None
    if note and len(note) > MAX_PRICE_NOTE:
        errors.append(f"«Источник цены» (price_note): не больше {MAX_PRICE_NOTE} символов")

    data: dict[str, object] = {}
    for name, raw in row.items():
        if name in PRICE_COLUMNS or raw == "":
            continue
        value: object
        if name in list_slots:
            items = [item.strip() for item in raw.split(LIST_SEPARATOR) if item.strip()]
            value = [_to_int_if_digits(i) for i in items] if name in int_literal_slots else items
        else:
            value = _to_int_if_digits(raw) if name in int_literal_slots else raw
        data[name] = value
    if price_kop is not None:
        data["price_kop"] = price_kop

    try:
        frame = frame_cls.model_validate(data)
    except ValidationError as exc:
        errors += describe_validation_error(exc, frame_cls)
        return None, errors
    if errors:
        return None, errors
    return CatalogRecord(frame=frame, price_checked_at=checked_at, price_note=note), []


def parse_catalog_csv(text: str, category: Category) -> CatalogParseResult:
    """Разбирает CSV категории: строки с ошибками формата отклоняются, остальные принимаются."""
    frame_cls = FRAMES_BY_CATEGORY[category]
    fields = frame_cls.model_fields.items()
    list_slots = frozenset(name for name, info in fields if _is_list_slot(info.annotation))
    int_literal_slots = frozenset(
        name for name, info in fields if _is_int_literal_slot(info.annotation)
    )
    result = CatalogParseResult()
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), strict=True)
    header = [column.strip() for column in reader.fieldnames or []]
    reader.fieldnames = header

    allowed = set(csv_columns(category))
    unknown = [column for column in header if column not in allowed]
    missing = [column for column in ("sku", "brand", "model", "price_rub") if column not in header]
    if unknown or missing:
        messages = [f"неизвестная колонка «{column}»" for column in unknown]
        messages += [f"нет обязательной колонки «{column}»" for column in missing]
        result.errors.append(RowError(line=1, messages=tuple(messages)))
        result.fatal = True
        return result

    seen_skus: dict[str, int] = {}
    for row in reader:
        line = reader.line_num
        if None in row:
            result.errors.append(RowError(line, ("в строке больше значений, чем колонок",)))
            continue
        cleaned = {key: (value or "").strip() for key, value in row.items()}
        if not any(cleaned.values()):
            continue
        record, errors = _parse_row(cleaned, frame_cls, list_slots, int_literal_slots)
        if record is not None and record.frame.sku in seen_skus:
            errors = [
                f"артикул {record.frame.sku} уже встречался в строке {seen_skus[record.frame.sku]}"
            ]
            record = None
        if record is None:
            result.errors.append(RowError(line, tuple(errors)))
            continue
        seen_skus[record.frame.sku] = line
        result.records.append(record)
    return result


@dataclass(slots=True)
class CatalogDirResult:
    """Результат чтения каталога из папки: записи всех категорий и ошибки по файлам."""

    records: list[CatalogRecord] = field(default_factory=list)
    errors: dict[str, list[RowError]] = field(default_factory=dict)
    missing_files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Нет ни одной ошибки."""
        return not any(self.errors.values())


def read_catalog_dir(directory: Path) -> CatalogDirResult:
    """Читает `<category>.csv` всех категорий; проверяет уникальность артикулов между файлами."""
    result = CatalogDirResult()
    sku_files: dict[str, str] = {}
    for category in Category:
        path = directory / f"{category.value}.csv"
        if not path.is_file():
            result.missing_files.append(path.name)
            continue
        parsed = parse_catalog_csv(path.read_text(encoding="utf-8"), category)
        errors = list(parsed.errors)
        for record in parsed.records:
            other = sku_files.get(record.frame.sku)
            if other is not None:
                message = f"артикул {record.frame.sku} уже есть в {other}"
                errors.append(RowError(line=None, messages=(message,)))
                continue
            sku_files[record.frame.sku] = path.name
            result.records.append(record)
        if errors:
            result.errors[path.name] = errors
    return result


def frame_to_csv_row(
    frame: Component, *, price_checked_at: date | None, price_note: str | None
) -> dict[str, str]:
    """Фрейм категории → строка CSV в формате `knowledge/catalog/README.md`.

    Списки — через `|`, логические — `true`/`false`, пустые слоты — пустая ячейка,
    `price_rub` — целые рубли (копейки отбрасываются).
    """
    data = frame.model_dump(mode="json")
    row: dict[str, str] = {}
    for name in csv_columns(frame.category):
        if name == "price_rub":
            row[name] = str(frame.price_kop // 100)
        elif name == "price_checked_at":
            row[name] = price_checked_at.isoformat() if price_checked_at is not None else ""
        elif name == "price_note":
            row[name] = price_note or ""
        else:
            value = data.get(name)
            if value is None:
                row[name] = ""
            elif isinstance(value, bool):
                row[name] = "true" if value else "false"
            elif isinstance(value, list):
                row[name] = LIST_SEPARATOR.join(str(item) for item in value)
            else:
                row[name] = str(value)
    return row


def dump_catalog_csv(
    rows: list[tuple[Component, date | None, str | None]], category: Category
) -> str:
    """CSV-файл категории: заголовок и строки по порядку колонок `csv_columns`."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=csv_columns(category), lineterminator="\n")
    writer.writeheader()
    for frame, checked_at, note in rows:
        writer.writerow(frame_to_csv_row(frame, price_checked_at=checked_at, price_note=note))
    return buffer.getvalue()

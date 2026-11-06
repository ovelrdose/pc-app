"""Разбор CSV каталога: формат, ошибки по-русски, уникальность артикулов."""

from pathlib import Path

from app.expert.frames import CPU, Category
from app.services.catalog_csv import csv_columns, parse_catalog_csv, read_catalog_dir

CPU_HEADER = (
    "sku,brand,model,socket,cores,threads,base_ghz,boost_ghz,tdp_w,igpu,mem_types,"
    "perf_single,perf_multi,price_rub,price_checked_at,price_note"
)
CPU_ROW = (
    "CPU-AMD-R5-7600,AMD,Ryzen 5 7600,AM5,6,12,3.8,5.1,65,true,DDR5,100,100,"
    "18990,2026-10-29,ориентир"
)


def test_csv_columns_follow_frame_slots() -> None:
    columns = csv_columns(Category.CPU)
    assert columns[:3] == ["sku", "brand", "model"]
    assert "price_kop" not in columns
    assert "category" not in columns
    assert columns[-3:] == ["price_rub", "price_checked_at", "price_note"]


def test_valid_row_becomes_frame_with_price_in_kopecks() -> None:
    result = parse_catalog_csv(f"{CPU_HEADER}\n{CPU_ROW}\n", Category.CPU)
    assert result.errors == []
    record = result.records[0]
    assert isinstance(record.frame, CPU)
    assert record.frame.price_kop == 1_899_000
    assert record.frame.mem_types == ["DDR5"]
    assert record.frame.igpu is True
    assert record.price_note == "ориентир"
    assert str(record.price_checked_at) == "2026-10-29"


def test_list_slot_split_by_pipe_and_empty_cell_uses_default() -> None:
    row = CPU_ROW.replace(",DDR5,", ",DDR4 | DDR5,").replace(",100,100,", ",,100,")
    record = parse_catalog_csv(f"{CPU_HEADER}\n{row}\n", Category.CPU).records[0]
    assert isinstance(record.frame, CPU)
    assert record.frame.mem_types == ["DDR4", "DDR5"]
    assert record.frame.perf_single is None


def test_bom_and_blank_lines_are_tolerated() -> None:
    result = parse_catalog_csv(f"﻿{CPU_HEADER}\n\n{CPU_ROW}\n,,,\n", Category.CPU)
    assert result.errors == []
    assert len(result.records) == 1


def test_row_errors_are_human_readable() -> None:
    row = CPU_ROW.replace(",6,12,", ",шесть,12,").replace(",18990,", ",,")
    result = parse_catalog_csv(f"{CPU_HEADER}\n{CPU_ROW}\n{row}\n", Category.CPU)
    assert len(result.records) == 1
    [error] = result.errors
    assert error.line == 3
    text = str(error)
    assert "строка 3" in text
    assert "«Цена, ₽» (price_rub): не заполнено" in text
    assert "«Ядер» (cores) = «шесть»: ожидается целое число" in text


def test_range_error() -> None:
    row = CPU_ROW.replace(",65,", ",9999,")
    [error] = parse_catalog_csv(f"{CPU_HEADER}\n{row}\n", Category.CPU).errors
    assert error.messages == ("«TDP» (tdp_w) = «9999»: должно быть не больше 400",)


def test_cross_slot_error() -> None:
    row = CPU_ROW.replace(",6,12,", ",8,4,")
    [error] = parse_catalog_csv(f"{CPU_HEADER}\n{row}\n", Category.CPU).errors
    assert error.messages == ("потоков не может быть меньше ядер",)


def test_int_choice_slots_accept_csv_strings() -> None:
    header = "sku,brand,model,size_mm,price_rub"
    [record] = parse_catalog_csv(f"{header}\nFAN-A,Arctic,P14,140,900\n", Category.CASE_FAN).records
    assert record.frame.model_dump()["size_mm"] == 140
    result = parse_catalog_csv(f"{header}\nFAN-B,Arctic,P13,130,900\n", Category.CASE_FAN)
    assert "допустимые значения: 80, 92, 120, 140 или 200" in str(result.errors[0])


def test_bad_price_and_date() -> None:
    row = CPU_ROW.replace(",18990,2026-10-29,", ",18990.50,29.10.2026,")
    [error] = parse_catalog_csv(f"{CPU_HEADER}\n{row}\n", Category.CPU).errors
    assert any("целое число рублей" in message for message in error.messages)
    assert any("ГГГГ-ММ-ДД" in message for message in error.messages)


def test_price_with_spaces_is_accepted() -> None:
    row = CPU_ROW.replace(",18990,", ",18 990,")
    [record] = parse_catalog_csv(f"{CPU_HEADER}\n{row}\n", Category.CPU).records
    assert record.frame.price_kop == 1_899_000


def test_unknown_and_missing_columns_reject_file() -> None:
    header = CPU_HEADER.replace("sku,", "").replace("perf_multi", "perf_mlti")
    result = parse_catalog_csv(f"{header}\n", Category.CPU)
    [error] = result.errors
    assert error.line == 1
    assert "неизвестная колонка «perf_mlti»" in error.messages
    assert "нет обязательной колонки «sku»" in error.messages


def test_duplicate_sku_in_file() -> None:
    result = parse_catalog_csv(f"{CPU_HEADER}\n{CPU_ROW}\n{CPU_ROW}\n", Category.CPU)
    assert len(result.records) == 1
    assert "уже встречался в строке 2" in str(result.errors[0])


def test_extra_values_in_row() -> None:
    result = parse_catalog_csv(f"{CPU_HEADER}\n{CPU_ROW},лишнее\n", Category.CPU)
    assert "больше значений, чем колонок" in str(result.errors[0])


def test_read_catalog_dir_detects_cross_file_duplicates(tmp_path: Path) -> None:
    (tmp_path / "cpu.csv").write_text(f"{CPU_HEADER}\n{CPU_ROW}\n", encoding="utf-8")
    fan_header = "sku,brand,model,size_mm,price_rub"
    (tmp_path / "case_fan.csv").write_text(
        f"{fan_header}\nCPU-AMD-R5-7600,Arctic,P12,120,900\n", encoding="utf-8"
    )
    result = read_catalog_dir(tmp_path)
    assert not result.ok
    assert "уже есть в cpu.csv" in str(result.errors["case_fan.csv"][0])
    assert "gpu.csv" in result.missing_files


def test_dump_catalog_csv_round_trip() -> None:
    """Фрейм → CSV-строка → фрейм: значения, списки, bool и цена в рублях сохраняются."""
    from datetime import date

    from app.services.catalog_csv import dump_catalog_csv, parse_catalog_csv

    text = f"{CPU_HEADER}\n{CPU_ROW}\n"
    parsed = parse_catalog_csv(text, Category.CPU)
    record = parsed.records[0]
    dumped = dump_catalog_csv(
        [(record.frame, record.price_checked_at, record.price_note)], Category.CPU
    )
    # экспорт пишет полный шаблон колонок (csv_columns), а не подмножество из файла
    assert dumped.splitlines()[0] == ",".join(csv_columns(Category.CPU))
    reparsed = parse_catalog_csv(dumped, Category.CPU)
    assert reparsed.errors == []
    assert len(reparsed.records) == 1
    again = reparsed.records[0]
    assert again.frame == record.frame
    assert again.price_checked_at == date(2026, 10, 29)
    assert again.price_note == "ориентир"


def test_dump_catalog_csv_formats_lists_bools_and_rubles() -> None:
    """Списки через `|`, bool как true/false, целые рубли, пустые ячейки для None."""
    from app.expert.frames import FRAMES_BY_CATEGORY
    from app.services.catalog_csv import dump_catalog_csv, frame_to_csv_row
    from tests.factories import slots

    frame = FRAMES_BY_CATEGORY[Category.CPU](
        **slots(
            Category.CPU,
            sku="CPU-TEST-CSV",
            mem_types=["DDR4", "DDR5"],
            igpu=False,
            perf_single=None,
            price_kop=123_499,
        )
    )
    row = frame_to_csv_row(frame, price_checked_at=None, price_note=None)
    assert row["mem_types"] == "DDR4|DDR5"
    assert row["igpu"] == "false"
    assert row["unlocked"] == "false"  # значение по умолчанию
    assert row["perf_single"] == ""  # незаполненный слот — пустая ячейка
    assert row["price_rub"] == "1234"  # копейки при экспорте в рубли отбрасываются
    assert row["price_checked_at"] == ""
    csv_text = dump_catalog_csv([(frame, None, None)], Category.CPU)
    header_tail = csv_text.splitlines()[0].split(",")[-3:]
    assert header_tail == ["price_rub", "price_checked_at", "price_note"]

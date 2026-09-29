"""Read-only verification that the checked-in config matches Нормативы.xlsx."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
import zipfile
from pathlib import Path

from app.core.enrichment_config import ENRICHMENT_CONFIG

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
NORMATIVES_PATH = WORKSPACE_ROOT / "Датасет" / "Нормативы.xlsx"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"m": MAIN_NS}


def _xlsx_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with zipfile.ZipFile(path) as archive:
        workbook = element_tree.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("m:sheets/m:sheet", NS)
        assert len(sheets) == 1
        shared_strings = element_tree.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = [
            "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
            for item in shared_strings
        ]
        worksheet = element_tree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for row in worksheet.findall(".//m:row", NS):
        values = []
        for cell in row.findall("m:c", NS):
            value = cell.find("m:v", NS)
            values.append(
                strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
            )
        rows.append(values)
    return [sheet.attrib["name"] for sheet in sheets], rows


def test_one_excel_worksheet_and_four_normatives_match_runtime_config() -> None:
    sheet_names, rows = _xlsx_rows(NORMATIVES_PATH)
    assert len(sheet_names) == 1
    assert len(rows) == 5
    excel_normatives = {row[0]: tuple(map(int, row[1:])) for row in rows[1:]}
    assert excel_normatives == {
        "Подключение клиентов Базовая": (20, 60, 10, 90),
        "Аварий на ТКД": (20, 80, 0, 100),
        "Дозаказ оборудования": (20, 10, 10, 40),
        "Локальная заявка/ремонт у клиента": (20, 30, 0, 50),
    }
    assert {
        item.work_name: (
            item.normative_travel_min,
            item.technical_work_min,
            item.documents_min,
            item.base_normative_min,
        )
        for item in ENRICHMENT_CONFIG.bk_normatives.values()
    } == excel_normatives

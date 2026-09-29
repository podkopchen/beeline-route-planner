"""Strict, read-only loader for the three permitted synthetic CSV inputs."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CSV_ENCODING: Final = "cp1251"
CSV_DELIMITER: Final = ";"

REQUIRED_COLUMNS: Final = frozenset(
    {
        "Заявка",
        "Тип заявки BK",
        "Тип заявки HD",
        "Начало",
        "Окончание",
        "Район",
        "Адрес",
        "Гигабитное подключение",
    }
)


@dataclass(frozen=True)
class SyntheticSource:
    """An approved source file and its stable territory key."""

    territory: str
    filename: str


SYNTHETIC_SOURCES: Final = (
    SyntheticSource("east", "Восток Синтетические данные.csv"),
    SyntheticSource("southeast", "Юго-восток Синтетические данные.csv"),
    SyntheticSource("southcenter", "Югоцентр Синтетические данные.csv"),
)


class CsvContractError(ValueError):
    """Raised when a permitted source violates the documented CSV contract."""


@dataclass(frozen=True)
class SourceRequest:
    """A valid source row, preserved before domain normalization in DATA-002."""

    territory: str
    source_order: int
    source_line: int
    source_request_id: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class OfficeLocation:
    """The office service row retained as a territory start-point source."""

    territory: str
    address: str
    source_line: int


@dataclass(frozen=True)
class LoadedTerritory:
    territory: str
    source_path: Path
    headers: tuple[str, ...]
    requests: tuple[SourceRequest, ...]
    office: OfficeLocation


@dataclass(frozen=True)
class LoadedSourceData:
    territories: tuple[LoadedTerritory, ...]

    @property
    def requests(self) -> tuple[SourceRequest, ...]:
        return tuple(
            request for territory in self.territories for request in territory.requests
        )

    @property
    def offices(self) -> tuple[OfficeLocation, ...]:
        return tuple(territory.office for territory in self.territories)


def permitted_source_paths(source_directory: Path) -> tuple[Path, ...]:
    """Return only the fixed allowlist; never discover arbitrary CSV files."""

    return tuple(source_directory / source.filename for source in SYNTHETIC_SOURCES)


def is_valid_source_request_id(value: str | None) -> bool:
    """A valid request ID contains ASCII digits only after surrounding whitespace."""

    candidate = (value or "").strip()
    return bool(candidate) and candidate.isascii() and candidate.isdigit()


def load_all_synthetic_sources(source_directory: Path) -> LoadedSourceData:
    """Load the three approved files in stable territory/input order."""

    return LoadedSourceData(
        territories=tuple(
            _load_territory(source_directory / source.filename, source.territory)
            for source in SYNTHETIC_SOURCES
        )
    )


def _load_territory(source_path: Path, territory: str) -> LoadedTerritory:
    if not source_path.is_file():
        raise CsvContractError(f"Synthetic source is missing: {source_path.name}")

    with source_path.open("r", encoding=CSV_ENCODING, newline="") as source_file:
        reader = csv.DictReader(source_file, delimiter=CSV_DELIMITER)
        headers = tuple(reader.fieldnames or ())
        _validate_headers(headers, source_path)

        requests: list[SourceRequest] = []
        office: OfficeLocation | None = None
        for row in reader:
            fields = {header: value or "" for header, value in row.items() if header}
            request_id = fields.get("Заявка", "")

            if is_valid_source_request_id(request_id):
                requests.append(
                    SourceRequest(
                        territory=territory,
                        source_order=len(requests),
                        source_line=reader.line_num,
                        source_request_id=request_id.strip(),
                        fields=fields,
                    )
                )
                continue

            if not any(value.strip() for value in fields.values()):
                continue

            if _is_office_row(request_id):
                if office is not None:
                    raise CsvContractError(
                        f"Multiple office rows in {source_path.name}"
                    )
                office = OfficeLocation(
                    territory=territory,
                    address=_office_address(fields, source_path),
                    source_line=reader.line_num,
                )
                continue

            raise CsvContractError(
                f"Unexpected non-request row at line {reader.line_num} "
                f"in {source_path.name}"
            )

    if office is None:
        raise CsvContractError(f"Office row is missing in {source_path.name}")

    return LoadedTerritory(
        territory=territory,
        source_path=source_path,
        headers=headers,
        requests=tuple(requests),
        office=office,
    )


def _validate_headers(headers: tuple[str, ...], source_path: Path) -> None:
    missing_columns = REQUIRED_COLUMNS.difference(headers)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise CsvContractError(f"Missing columns in {source_path.name}: {missing}")


def _is_office_row(value: str) -> bool:
    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    return normalized == "адресофиса"


def _office_address(fields: Mapping[str, str], source_path: Path) -> str:
    values_after_marker = list(fields.values())[1:]
    address = next(
        (value.strip() for value in values_after_marker if value.strip()), ""
    )
    if not address:
        raise CsvContractError(f"Office address is empty in {source_path.name}")
    return address

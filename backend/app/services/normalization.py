"""Normalization from the DATA-001 loader contract to strict Pydantic models."""

from __future__ import annotations

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from app.models.normalized_dataset import (
    NormalizedDataset,
    NormalizedOffice,
    NormalizedRequest,
)
from app.services.csv_loader import LoadedSourceData, SourceRequest

MOSCOW_TIMEZONE: Final = ZoneInfo("Europe/Moscow")
SOURCE_DATETIME_FORMAT: Final = "%d.%m.%Y %H:%M"


class NormalizationError(ValueError):
    """Raised when a loaded source row cannot become a complete domain record."""


def normalize_loaded_source_data(loaded_data: LoadedSourceData) -> NormalizedDataset:
    """Normalize every allowlisted source while preserving source and file order."""

    requests = tuple(
        _normalize_request(request, territory.source_path.name)
        for territory in loaded_data.territories
        for request in territory.requests
    )
    offices = tuple(
        NormalizedOffice(
            office_id=f"office:{territory.territory}",
            territory=territory.territory,
            source_filename=territory.source_path.name,
            source_line=territory.office.source_line,
            source_address=territory.office.address,
        )
        for territory in loaded_data.territories
    )
    return NormalizedDataset(requests=requests, offices=offices)


def _normalize_request(
    request: SourceRequest,
    source_filename: str,
) -> NormalizedRequest:
    fields = dict(request.fields)
    connection = fields.get("Подключение", "").strip() or None
    return NormalizedRequest(
        request_id=f"{request.territory}:{request.source_request_id}",
        source_request_id=request.source_request_id,
        source_order=request.source_order,
        source_line=request.source_line,
        territory=request.territory,
        source_filename=source_filename,
        source_address=_required_source_value(request, "Адрес"),
        district=_required_source_value(request, "Район"),
        bk_request_type=_required_source_value(request, "Тип заявки BK"),
        hd_request_type=_required_source_value(request, "Тип заявки HD"),
        gigabit_connection=_required_source_value(request, "Гигабитное подключение"),
        connection=connection,
        window_start=_parse_source_datetime(request, "Начало"),
        window_end=_parse_source_datetime(request, "Окончание"),
        source_fields=fields,
    )


def _required_source_value(request: SourceRequest, column: str) -> str:
    value = request.fields.get(column, "")
    if not value.strip():
        raise NormalizationError(
            f"Request {request.source_request_id} has empty required {column!r}"
        )
    return value


def _parse_source_datetime(request: SourceRequest, column: str) -> datetime:
    raw_value = _required_source_value(request, column)
    try:
        parsed = datetime.strptime(  # noqa: DTZ007 -- source has no timezone column.
            raw_value, SOURCE_DATETIME_FORMAT
        )
    except ValueError as error:
        raise NormalizationError(
            f"Request {request.source_request_id} has invalid {column!r}: {raw_value!r}"
        ) from error
    return parsed.replace(tzinfo=MOSCOW_TIMEZONE)

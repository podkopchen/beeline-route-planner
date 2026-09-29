"""Versioned deterministic DATA-003 rules, transcribed from Нормативы.xlsx."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

ENRICHMENT_SEED: Final = 2026


@dataclass(frozen=True)
class WorkNormative:
    """One authoritative work norm; travel is informational, never route time."""

    work_name: str
    normative_travel_min: int
    technical_work_min: int
    documents_min: int

    @property
    def service_duration_min(self) -> int:
        return self.technical_work_min + self.documents_min

    @property
    def base_normative_min(self) -> int:
        return self.normative_travel_min + self.service_duration_min


@dataclass(frozen=True)
class EnrichmentConfig:
    """All deterministic enrichment inputs; no random sampling is permitted."""

    seed: int
    bk_skill_rules: dict[str, str]
    bk_normatives: dict[str, WorkNormative]
    high_complexity_bk_types: frozenset[str]
    high_complexity_hd_types: frozenset[str]
    low_complexity_hd_types: frozenset[str]
    vehicle_connection_values: frozenset[str]
    gigabit_yes_values: frozenset[str]


# Source: Датасет/Нормативы.xlsx, its only worksheet, verified 2026-09-16.
ENRICHMENT_CONFIG: Final = EnrichmentConfig(
    seed=ENRICHMENT_SEED,
    bk_skill_rules={
        "Подключение": "installation",
        "Локальная заявка": "subscriber_support",
        "Дозаказ": "subscriber_support",
        "Глобальная проблема": "network_repair",
    },
    bk_normatives={
        "Подключение": WorkNormative("Подключение клиентов Базовая", 20, 60, 10),
        "Глобальная проблема": WorkNormative("Аварий на ТКД", 20, 80, 0),
        "Дозаказ": WorkNormative("Дозаказ оборудования", 20, 10, 10),
        "Локальная заявка": WorkNormative(
            "Локальная заявка/ремонт у клиента", 20, 30, 0
        ),
    },
    high_complexity_bk_types=frozenset({"Глобальная проблема"}),
    high_complexity_hd_types=frozenset(
        {"Авария", "Нет линка", "Разрывы", "Работа с кабелем", "Рост ошибок на порту"}
    ),
    low_complexity_hd_types=frozenset({"Информация", "Мониторинг"}),
    vehicle_connection_values=frozenset({"FTTB"}),
    gigabit_yes_values=frozenset({"Да"}),
)

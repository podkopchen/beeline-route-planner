# RouteFlow — словарь нормализованных данных

## Производные road-cache файлы

`road_matrix_cache.json`: `origin_cache_key`, `destination_cache_key`, distance km, base duration min, mode/source/status; GeoJSON отсутствует. `road_geometry_cache.json`: только pair keys и GeoJSON LineString для выбранных car legs. Оба файла производны от legacy warm cache и не являются исходными данными.

Этот документ описывает контракт `DATA-002`. Нормализация читает только три
явно разрешённых synthetic CSV через `app.services.csv_loader`; закрытые файлы
«Контрольное распределение» в неё не входят. Исходные CSV не перезаписываются.

Время источника читается строго в формате `DD.MM.YYYY HH:MM` и сохраняется как
timezone-aware `datetime` в `Europe/Moscow` (`+03:00`). Значение окончания
окна не генерируется: пустое или некорректное `Окончание` завершает
нормализацию ошибкой. В текущих трёх источниках оно заполнено для всех 205
заявок.

## `NormalizedRequest`

| Поле | Источник / правило | Тип | Nullable | Пример |
|---|---|---|---|---|
| `request_id` | `territory + ":" + source_request_id` | `str` | Нет | `east:74198` |
| `source_request_id` | CSV `Заявка`, ASCII-цифры после trim | `str` | Нет | `74198` |
| `source_order` | Нулевой индекс валидной заявки в её CSV | `int >= 0` | Нет | `0` |
| `source_line` | Физическая строка CSV, которую сообщил `csv.DictReader` | `int >= 2` | Нет | `2` |
| `territory` | Фиксированный allowlist loader: `east`, `southeast`, `southcenter` | literal | Нет | `east` |
| `source_filename` | Имя allowlisted CSV | `str` | Нет | `Восток Синтетические данные.csv` |
| `source_address` | CSV `Адрес`, сохраняется без изменения | `str` | Нет | `г. Москва, ...` |
| `district` | CSV `Район`, сохраняется без изменения | `str` | Нет | `Кузьминки` |
| `bk_request_type` | CSV `Тип заявки BK`, сохраняется без изменения | `str` | Нет | `...` |
| `hd_request_type` | CSV `Тип заявки HD`, сохраняется без изменения | `str` | Нет | `...` |
| `gigabit_connection` | CSV `Гигабитное подключение`, сохраняется без изменения | `str` | Нет | `Да` |
| `connection` | CSV `Подключение`: trim; пустая или отсутствующая колонка → `null` | `str \| null` | Да | `FMC` / `null` |
| `window_start` | CSV `Начало`, `DD.MM.YYYY HH:MM` → `Europe/Moscow` | `datetime` | Нет | `2026-08-17T10:00:00+03:00` |
| `window_end` | CSV `Окончание`, тот же формат; пустое/некорректное значение — ошибка | `datetime` | Нет | `2026-08-17T12:00:00+03:00` |
| `source_fields` | Полный словарь исходной строки: все заголовки и их исходные строковые значения | `dict[str, str]` | Нет | `{ "Заявка": "74198", ... }` |

«Значимые» явные поля выше дублируют исходные значения для типизированного
потребления, а `source_fields` сохраняет их полный источник и не теряет
неизвестные будущие колонки.

## `NormalizedOffice`

| Поле | Источник / правило | Тип | Nullable | Пример |
|---|---|---|---|---|
| `office_id` | `"office:" + territory` | `str` | Нет | `office:east` |
| `territory` | Allowlist loader | literal | Нет | `east` |
| `source_filename` | Имя CSV территории | `str` | Нет | `Восток Синтетические данные.csv` |
| `source_line` | Физическая строка служебной строки офиса | `int >= 2` | Нет | `69` |
| `source_address` | Адрес после маркера `Адрес офиса` в служебной строке | `str` | Нет | `г. Москва, ул Юных Ленинцев, д 83с 4` |

Офис хранится только в `NormalizedDataset.offices` и не появляется в
`NormalizedDataset.requests`.

## `NormalizedDataset`

| Поле | Источник / правило | Тип | Nullable | Пример |
|---|---|---|---|---|
| `requests` | Нормализованные записи в порядке файлов allowlist и `source_order` внутри файла | `tuple[NormalizedRequest, ...]` | Нет | 205 записей |
| `offices` | Один нормализованный офис на территорию, в порядке allowlist | `tuple[NormalizedOffice, ...]` | Нет | 3 записи |

## `EnrichedRequest` (DATA-003)

Все поля этого раздела — `derived/synthetic`: их нет в CSV. Правила находятся
в `app.core.enrichment_config`, конфиг неизменяем, а `seed = 2026` включён в
результат. Текущие правила не используют случайные выборки: одинаковый
нормализованный вход и конфиг всегда дают один canonical JSON (sorted keys,
compact separators, UTF-8) и один SHA-256.

| Поле | Статус / правило генерации | Тип | Nullable | Пример |
|---|---|---|---|---|
| `required_skills` | derived; строго один навык из `Тип заявки BK`: `Подключение` → `installation`, `Локальная заявка`/`Дозаказ` → `subscriber_support`, `Глобальная проблема` → `network_repair` | `tuple[skill, ...]` | Нет | `["installation"]` |
| `complexity` | derived; `high` для BK `Глобальная проблема` либо HD `Авария`, `Нет линка`, `Разрывы`, `Работа с кабелем`, `Рост ошибок на порту`; `low` для HD `Информация`/`Мониторинг`; иначе `medium` | `low \| medium \| high` | Нет | `high` |
| `normative_work_name` | derived from CSV `Тип заявки BK` through the transcribed `Датасет/Нормативы.xlsx` mapping | `str` | Нет | `Подключение клиентов Базовая` |
| `technical_work_min` | derived normative technical work: BK `Подключение`/`Глобальная проблема`/`Дозаказ`/`Локальная заявка` → 60/80/10/30 | `int` | Нет | `60` |
| `documents_min` | derived normative documents: same BK order → 10/0/10/0 | `int` | Нет | `10` |
| `service_duration_min` | derived `technical_work_min + documents_min`; 70/80/20/30 for the four BK types. This is the only on-site duration consumed by baseline and future VRPTW. Unknown BK is a validation error, never a fallback. | `int` | Нет | `70` |
| `normative_travel_min` | derived Excel reference travel: 20 minutes for every current BK normative. Stored for transparency only; never added to matrix/Haversine travel time. | `int` | Нет | `20` |
| `base_normative_min` | derived `normative_travel_min + service_duration_min`; Excel full norm 90/100/40/50 | `int` | Нет | `90` |
| `priority` | synthetic; все начальные заявки имеют `normal`. `urgent` создаётся только будущим сценарием событий/replan | `normal \| urgent` | Нет | `normal` |
| `transport_requirement` | derived; `car` при `complexity=high`, `connection=FTTB` или `gigabit_connection=Да`; иначе `none` | `none \| car` | Нет | `car` |

`EnrichedDataset` повторно использует неизменённые `requests` и `offices` из
DATA-002, добавляя только `enrichment_seed=2026` и новые derived-поля заявок.
Офисы, инженеры, координаты и маршруты на этой стадии не создаются.

## `Engineer` и `WorkforceDataset` (DATA-004)

Инженеры — полностью synthetic, анонимные и детерминированные. Их нет в CSV:
DATA-004 создаёт 12 `east`, 12 `southeast`, 11 `southcenter` по неизменяемому
шаблону `workforce_config`, с `workforce_seed=2026`. У всех смена
10:00–22:00 `Europe/Moscow`: она пересекается с каждым окном текущих заявок.
Каждая территория содержит минимум двух инженеров `car` для каждого из трёх
навыков; для любой текущей заявки находятся минимум два локальных кандидата.

| Поле | Статус / правило генерации | Тип | Nullable | Пример |
|---|---|---|---|---|
| `engineer_id` | synthetic stable ID `eng-{territory}-{01..12}` | `str` | Нет | `eng-east-01` |
| `territory` | synthetic территория шаблона | `east \| southeast \| southcenter` | Нет | `east` |
| `office_id` | source-derived ссылка на DATA-002 office той же территории | `str` | Нет | `office:east` |
| `shift_start`, `shift_end` | synthetic 10:00 и 22:00 дня заявок в `Europe/Moscow` | `datetime` | Нет | `2026-08-17T10:00:00+03:00` |
| `skills` | synthetic controlled vocabulary: `installation`, `subscriber_support`, `network_repair`; шаблон содержит 1–2 навыка | `tuple[skill, ...]` | Нет | `["network_repair"]` |
| `available_transport` | synthetic controlled vocabulary `none`/`car`; по два `car`-инженера на навык в территории | `none \| car` | Нет | `car` |
| `level` | synthetic отображаемый уровень, не персональные данные: `junior`/`middle`/`senior` | `str` | Нет | `middle` |

`TerritoryCapacity` — производный sanity-report: service-only demand сравнивается
с суммой сменных минут. В DATA-004 дорожное время не учитывается и не является
утверждением выполнимости будущего маршрута.

## `PlanningEvent` (DATA-004)

События отделены от базового пула 205 заявок и не запускают перепланирование
на этой стадии. В каждой территории ровно три события: `urgent_request`,
`request_cancellation`, `engineer_unavailable`. Все имеют timezone-aware
`occurred_at`, территорию, typed payload, текстовый effect и `changes_plan`.

| Тип | Payload | Эффект |
|---|---|---|
| `urgent_request` | `UrgentRequestPayload`: `synthetic_event_data=true`, synthetic ID, urgent priority, навык, транспорт, длительность и окно | Добавляет новую synthetic event request только будущему replan; не является строкой CSV |
| `request_cancellation` | `target_request_id` | Удаляет указанную исходную заявку из будущего плана |
| `engineer_unavailable` | ID инженера и интервал недоступности | Исключает инженера из будущего плана на интервал |

Основной будущий сценарий — `event-east-urgent-1430`: 17.08.2026 14:30
`Europe/Moscow`, новая synthetic urgent заявка `network_repair` + `car`,
80 минут on-site service по нормативу «Аварий на ТКД», окно 15:00–17:00. Он помечен `changes_plan=true` и предназначен для
`REPLAN-001`; DATA-004 план не пересчитывает.

## `GeoCacheEntry`, `GeoTarget` и `TravelMetric` (GEO-001)

GEO-001 не делает сетевых вызовов при import, backend runtime или UI. Кэш
собирается явной командой `backend\.venv\Scripts\python.exe
scripts\build_geocache.py` из 205 request-адресов, трёх офисов и трёх адресов
synthetic urgent events. На старте нет пригодного локального кэша, поэтому
`data/generated/geocache.json` содержит 201 уникальный нормализованный адрес
со статусом `unresolved`; повторы адресов используют один cache key.

| Поле | Статус / правило | Тип | Nullable | Пример |
|---|---|---|---|---|
| `normalized_address` | derived: casefold, пунктуация → пробел, схлопывание whitespace | `str` | Нет | `г москва ул тестовая 1` |
| `cache_key` | derived: SHA-256 UTF-8 от `normalized_address` | `str` | Нет | `8f...` |
| `coordinates` | кэшированные координаты; только validated local/manual или явный Nominatim build | `{latitude, longitude} \| null` | Да | `null` |
| `source` | storage source: `nominatim`, `synthetic_proxy`, `manual_cache` или `unresolved` | literal | Нет | `synthetic_proxy` |
| `geo_source` | provenance для UI/API: `nominatim`, `synthetic_proxy`, `legacy_unknown` или `unresolved` | literal | Нет после GEO-001 | `synthetic_proxy` |
| `status` | `resolved` только с координатами, иначе `unresolved` | literal | Нет | `unresolved` |
| `warning` | обязателен по смыслу при unresolved/сомнительных координатах; не скрывает отсутствие точки | `str \| null` | Да | `Coordinates are unavailable...` |
| `query_variant` | derived: вариант явной Nominatim цепочки (`raw_freeform`, `normalized_freeform`, `structured_street`) | literal \| `null` | Да | `structured_street` |
| `display_name` | Nominatim result label только для принятого кандидата; не заменяет исходный адрес | `str \| null` | Да | `улица Юных Ленинцев, Москва, Россия` |
| `precision` | `house`/`street` Nominatim; `synthetic_proxy` для offline proxy; `legacy_unknown` для старого кэша | literal | Нет после GEO-001 | `synthetic_proxy` |
| `approximate` | `false` только для `house`; `true` для street, proxy и legacy_unknown | `bool` | Нет после GEO-001 | `true` |
| `geocode_attempted` | derived build checkpoint: цепочка для ключа завершена и не будет автоматически повторена при resume | `bool` | Нет | `true` |
| `location_source_request_id` | only urgent event: ID существующей заявки, чьи координаты унаследованы | `str \| null` | Да | `east:12345` |
| `GeoTarget.target_kind` | provenance: `request`, `office`, `synthetic_event` | literal | Нет | `synthetic_event` |
| `TravelMetric.distance_km` | derived road-factor расстояние в километрах; `null`, если хотя бы одна точка unresolved | `float \| null` | Да | `13.91` |
| `TravelMetric.travel_minutes` | derived `ceil(distance_km / 25 km/h × 60)`; `null` для unresolved | `int \| null` | Да | `34` |

Fallback использует Haversine с радиусом Земли `6371.0088 km`, затем
`road_distance_factor=1.25` и `average_speed=25 km/h`. Он детерминирован,
симметричен и возвращает `0 km`/`0 min` на диагонали. OSRM не вызывается и
оставлен будущим опциональным adapter. Online Nominatim разрешён только через
`scripts/build_geocache.py --online`: user-agent `RouteFlow-Hackathon/0.1
(offline-first geocache builder)`, throttle 1.0 s, cache-first; synthetic
event-addresses онлайн не отправляются.

## `TrafficProfile` и сценарное время поездки (TIME-001)

`TrafficProfile` — typed offline MVP contract для будущих API/UI. Это **сценарий
загруженности**, не «текущие пробки», не live-данные и не историческая модель
конкретных дорог. Runtime не обращается к внешним источникам.

| `profile_id` | Отображаемое имя | `traffic_factor` |
|---|---|---:|
| `standard` | Обычная загрузка | 1.00 |
| `moderate` | Умеренная загруженность | 1.15 |
| `peak` | Пиковая загруженность | 1.35 |

Для уже рассчитанного Haversine road-factor distance сервис сохраняет
`base_unrounded_travel_minutes`, `base_travel_minutes=ceil(base)` и итоговое
`travel_minutes=ceil(base_unrounded_travel_minutes × traffic_factor)`. Округление
производится один раз после коэффициента; для `standard` это идентично прежнему
расчёту. Нулевая пара всегда имеет 0 минут. Меняются только минуты фактического
движения: километраж, `technical_work_min`, `documents_min`,
`service_duration_min`, `normative_travel_min` и `base_normative_min` не меняются.

`BaselinePlan` и каждый `BaselineStop` несут ID/factor выбранного профиля и
base/final inbound travel minutes для будущих DTO. Один профиль выбирается для
всего запуска; почасовой/дневной traffic model в TIME-001 отсутствует.

## `OptimizedPlan` и OR-Tools VRPTW (OPT-001)

`OptimizedPlan` строится локальным OR-Tools RoutingModel без сетевых вызовов.
Он принимает `all`/территорию и один `TrafficProfile`; в `all` территория
остаётся hard constraint. Узел старта каждого engineer-а — его office, а end
node имеет нулевые distance/travel cost: сервис последней заявки учитывается
до конца смены, но возврат в office не добавляется.

| Поле | Правило | Тип |
|---|---|---|
| `OptimizedStop.planned_arrival/service_start/service_end` | Решение Time dimension с окном, ожиданием, фактическим traffic-profile travel и `service_duration_min` | `datetime` |
| `base_travel_from_previous_minutes`, `travel_from_previous_minutes` | Тот же offline travel contract, что BASE-001/TIME-001 | `int` |
| `OptimizedRoute.total_*` | Сумма только фактических inbound legs/stops маршрута; no return-to-office | `int` / `float` |
| `OptimizedPlan.unassigned` | Только ID неназначенной заявки; OPT-001 намеренно не создаёт неподтверждённые причины | tuple |
| `objective_weights` | Вычисленные safe integer bounds для priority coverage → active engineers → distance | model |

Стоимость OR-Tools задаётся строго лексикографически. При верхней границе
расстояния `D`, `active_engineer_penalty=D+1`, а
`unassigned_request_penalty=vehicle_count × (D+1) + D + 1`. Поэтому никакое
возможное улучшение километров не компенсирует дополнительного инженера, а
никакое улучшение инженеров/километров не компенсирует потерю заявки. Время
поездки — hard constraint, но не objective.

## Единые метрики и diagnostics (OPT-002)

`calculate_plan_metrics(plan, enriched, workforce)` — один typed read-only
расчёт для `BaselinePlan` и `OptimizedPlan`. Он использует только сохранённые
inbound visit legs, поэтому no-return сохраняется: нормативные 20 минут дороги
не добавляются.

| Уровень | Поля |
|---|---|
| Route / engineer | `distance_km`, `travel_minutes`, `service_minutes`, `waiting_minutes`, `route_end`, `route_duration_minutes`, `visit_count` |
| Territory | assignment/unassigned/active counts и суммы distance/travel/service/waiting |
| Plan | assignment/unassigned/active counts, profile и суммы, плюс route/territory breakdown |

`DiagnosticReport` относится к unassigned `OptimizedPlan`. Каждый ID получает
ровно один code и проверяемые counts: инженеры территории/skill/transport,
отдельно feasible engineers, checked routes/positions и traffic profile. Codes:
`no_territory_engineer`, `skill_uncovered`, `transport_uncovered`,
`window_shift_infeasible`, `final_plan_insertion_infeasible`. Последний означает только отсутствие позиции
в **зафиксированном найденном** маршруте без изменения существующих визитов;
это не утверждение, что глобального решения нет. Feasible fixed-plan insertion
— внутренний invariant failure, а не публичная причина отказа. Тексты — короткие
русские UI-ready сообщения без LLM.

После остановки внешнего геокодирования GEO-001 завершает 46 остаточных keys
offline-обогатителем с seed `2026`. `synthetic_proxy` — не геокодирование и не
реальный адрес: это детерминированный небольшой разброс вокруг resolved-кластера
той же территории и локальности (Кашира/Ступино не смешиваются с Москвой).
Urgent-события не получают собственный выдуманный адрес: они наследуют
координаты существующей заявки своей территории через `location_source_request_id`.
## API-001 public projection

## REPLAN-001 event duration provenance

Synthetic urgent events keep `priority=urgent`, `network_repair`, `car` and their event time window, but their `service_duration_min` is derived from the authoritative NORM-001 `Глобальная проблема` mapping (`technical_work_min=80`, `documents_min=0`). Synthetic event defaults cannot override this value; a former 90-minute assumption is not stored.

`reserve-east-emergency-01` is an incident-only synthetic operational resource: `network_repair`, `car`, start `office:east`, activation at an urgent event effective time. It is absent from the 35-person canonical workforce and all baseline/optimized canonical metrics; a replan response explicitly marks its activation.

## EXPL-001 explanations

`RequestExplanation` is a deterministic read-only projection of an existing stop, route metric and verified diagnostic. `final_plan_insertion_infeasible` retains its fixed-plan scope and is never presented as global infeasibility.

Read-only API DTOs project local plan snapshots without changing source data. Request and stop timestamps are timezone-aware ISO-8601 values. Coordinates retain source, precision, approximate and warning, so synthetic/legacy points are not represented as exact. Optimized unassigned records expose one evidence diagnostic; `final_plan_insertion_feasible` is internal only.

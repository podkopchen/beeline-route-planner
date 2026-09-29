# RouteFlow

Диспетчерская выездных инженеров для хакатона Beeline Business: планирование смены, карта маршрутов, сравнение с baseline, события и проверяемые объяснения назначений.

React · TypeScript · MapLibre · FastAPI · Pydantic · OR-Tools

## Возможности и статус

- 205 synthetic-заявок, 35 regular-инженеров, три территории и три офиса.
- Учёт навыков, транспорта, временных окон, смен и нормативов работ.
- Baseline в исходном порядке; OR-Tools VRPTW с приоритетом покрытия, числа инженеров, километража.
- Векторная карта OpenFreeMap, офлайн-схема, дорожная геометрия из кэша и по запросу.
- Локальная demo-авторизация, сравнение планов, объяснения без LLM.
- Liquid Glass UI с SVG-логотипом и поддержкой reduced-motion.

Контрольный результат **fallback_only / all / standard**: 157 назначено, 48 неназначено, 25 активных инженеров. Для того же fallback-режима East urgent 14:30: прибытие резерва 14:44, обслуживание 15:00–16:20. Дорожный режим может давать другие показатели.

**Известные ограничения:** replan пока не выполняет полную VRPTW-переоптимизацию остатка смены; открыты вопросы отмены промежуточного визита, резервов и полноты diff. См. [аудит](docs/qa-audit-2026-09-29.md). Первое найденное решение OR-Tools не является доказательством глобального оптимума.

## Быстрый старт · Windows

Нужны Python 3.11+ и Node.js 20+; проверки выполнялись на Python 3.12. Выполняйте команды из корня клонированного репозитория.

### 1. Данные организатора

Исходные материалы не публикуются вместе с кодом. Перед запуском разместите предоставленные организатором файлы рядом с репозиторием:

```text
workspace/
├── beeline-route-planner/              # этот репозиторий
└── Датасет/
    ├── Нормативы.xlsx                  # нужен тесту соответствия нормативов
    └── Обезличивание/
        ├── Восток Синтетические данные.csv
        ├── Юго-восток Синтетические данные.csv
        └── Югоцентр Синтетические данные.csv
```

Содержимое и оригинальные имена этих четырёх файлов сохраняются. Control CSV не требуются и не читаются. Все имена файлов самого репозитория — ASCII. Обязательный геокэш и разделённые дорожные кэши находятся в `data/generated/`.

### 2. Установка

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
npm.cmd --prefix frontend ci
```

### 3. Запуск

В первом окне PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-api.ps1
```

Во втором окне, из того же корня:

```powershell
npm.cmd --prefix frontend run dev
```

- UI: http://localhost:5173
- Health: http://127.0.0.1:8000/health
- OpenAPI: http://127.0.0.1:8000/docs
- Demo-вход: `dispatcher` / `RouteFlow2026!`

`start.bat` запускает те же два сервиса. Остановка — Ctrl+C в терминалах запуска. Process-scoped execution policy не меняет системные настройки и не требует администратора.

Demo-пароль публичный и пригоден только для локального показа. Задайте `ROUTEFLOW_DEMO_USERNAME` и `ROUTEFLOW_DEMO_PASSWORD` в окружении перед запуском для собственных данных. `.env.example` документирует настройки; backend автоматически файл `.env` не читает. Сессия использует HttpOnly cookie. Используйте одинаковое имя хоста UI/API (`localhost`); подробности — [API](docs/api.md).

## Карта и сеть

Онлайн-подложка — OpenFreeMap Liberty с атрибуцией OpenFreeMap/OpenMapTiles/OpenStreetMap. При недоступности сети или WebGL остаётся локальная схема. 3D наклоняет камеру и показывает здания, если они доступны в style.

Launcher выбирает `road_if_available`. При открытии маршрута с отсутствующей геометрией выполняется явный запрос к `ROUTEFLOW_ROUTE_GEOMETRY_URL` (в demo — публичный OSRM). Канонический план этим запросом не пересчитывается. Для эксплуатации и новых точек нужен self-hosted routing service; кэш сам по себе не строит дороги. Геокодирование новых адресов не реализовано.

Координаты могут быть street/proxy/approximate. Загруженность — модельные сценарии, **не текущие пробки**. Для полностью офлайн-планировщика задайте перед запуском `$env:ROUTEFLOW_ROUTING_MODE = 'fallback_only'`.

## Проверки

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
```

Команда выполняет backend Ruff/pytest и frontend lint/typecheck/test/build; при ошибке останавливается. Отдельные команды:

```powershell
.\backend\.venv\Scripts\python.exe -m ruff check backend/app backend/tests scripts
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

## Структура

| Каталог | Назначение |
| --- | --- |
| `backend/app/` | API, typed-модели, конфиги, сервисы и репозитории |
| `backend/tests/` | Unit/integration и контроль неизменности данных |
| `frontend/src/` | Диспетчерский UI, карта и frontend-тесты |
| `data/generated/` | Обязательный геокэш и компактные road caches |
| `scripts/` | Запуск, проверки и явная подготовка данных |
| `docs/` | Архитектура, API, ограничения, QA и инструкции |

Начните с [оглавления документации](docs/README.md). [Подготовка к Git](docs/publishing.md) · [Правила разработки](CONTRIBUTING.md).

## Если не запускается

- Нет зависимостей: повторите команды установки.
- Нет исходных данных: проверьте структуру соседнего `Датасет/`.
- Порт 8000/5173 занят: остановите прежний процесс; не запускайте второй экземпляр.
- UI сообщает об ошибке API: проверьте health, процесс backend и одинаковый hostname.
- Нет дорог или подложки: проверьте доступность сервиса; пунктир означает отсутствие дорожной геометрии.

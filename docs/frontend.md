# RouteFlow dispatcher UI

## UX-коррекция типографики и отказов — 22 сентября 2026

Вход в неназначенные заявки теперь единственный: вкладка правой панели. Кнопка «Открыть подробнее ↗» открывает native modal dialog с адресом, окном, длительностью и существующим diagnostic; explanation загружается по выбору заявки. Закрытие кнопкой/Escape возвращает фокус и сохраняет маршрут/вкладку. Modal использует браузерное удержание фокуса; на узком экране карточки выстраиваются в одну колонку.

Шкала текста: 11 px служебные пометки, 12 px компактные подписи, 13 px основной текст и кнопки, 16 px заголовки панелей. KPI сохраняют крупный размер. Селекты имеют единые высоту 36 px, границы, focus/hover и dark color scheme; компактные элементы карты 32 px. Формы маркеров не изменены. Дублирующий верхний пункт удалён; «Карта маршрутов» закрывает сравнение, сохраняя текущую вкладку справа.

## Диспетчерский пульт — 22 сентября 2026

Текущая компоновка заменяет белые плавающие карточки графитовыми панелями вокруг светлой карты. Сверху — рабочая навигация (маршруты, неназначенные, сравнение), слева — единый прокручиваемый поток настроек/KPI/события, справа — список или подробности выбранного маршрута. При закрытии подробностей возвращается список. Сравнение открывается отдельным окном; Escape закрывает его. Все показатели берутся из существующих API DTO.

CSS переписан как единая система, старые конфликтующие слои заменены. Размеры боковых колонок заданы через `--left`/`--right`; карта использует их при fitBounds. По высоте панели ограничены viewport; длинный контент прокручивается внутри колонок. Легенда, выбор участка и 2D/3D имеют отдельные зоны. Размеры DOM-маркеров изолированы от кнопок; transform маркеров остаётся под управлением MapLibre.

Анимации 160–220 ms применены к раскрытию, деталям и hover. `prefers-reduced-motion` отключает motion. Скрытые настройки/маршруты имеют `hidden`, поэтому не остаются в клавиатурной навигации. Иконки — локальный SVG, шрифты — системные, дополнительных внешних ресурсов нет.

Проверки: frontend lint/typecheck/Vitest/build. Визуальная приёмка 1366×768 и 1920×1080 пока не подтверждена: in-app browser недоступен, запуск отдельного headless Edge отклонён политикой исполнения. Проверить вручную: общий экран → collapse/expand → маршрут и timeline → вкладка отказов → сравнение и Escape → East urgent и reset → стрелки/выбор leg → 2D/3D. Нельзя считать скриншот или WebGL проверенными только по unit-тестам.

## Visual refresh (2026-09-21)

- Интерфейс использует компактную operational UI-систему: радиус 2–3 px, тонкие разделители, единая типографическая иерархия, жёлтый акцент только для выбранных/важных состояний. Нативно выглядящие default HTML controls заменены сегментированными переключателями и стилизованными select.
- Панель параметров смены и правая панель маршрутов сворачиваются независимо. Их внутреннее состояние, выбранная вкладка и активный маршрут сохраняются; карта не пересоздаётся.
- В правой панели доступны tabs «Маршруты / Неназначенные». Timeline, explanation, scenario diff и comparison раскрываются поверх карты и не меняют workspace layout.
- Анимации короткие (140–220 ms): раскрытие панелей, drawer, hover и status pulse. При `prefers-reduced-motion` они практически отключены.
- Visual QA на 1366×768 требуется выполнить вручную: browser preview в среде разработки недоступен. Проверить отсутствие body-scroll, раскрытие comparison, обе collapse-кнопки, drawer, scenario и reset.

## Направление и выбор участка (2026-09-21)

- На online-карте белые шевроны движутся по GeoJSON выбранного дорожного маршрута от офиса к визитам. Это только указатель направления, не live-положение инженера. Новых запросов и изменения координат/расчётов нет.
- Нажатие на участок оставляет его цветным с белой обводкой, приглушает остальные линии и открывает карточку с направлением, номером, минутами и километрами. Повторное нажатие или «Снять выделение» возвращает обзор.
- Для совпадающих линий используйте список «Участок» внизу карты: «Офис → 1», «1 → 2» и т. д.; он доступен с клавиатуры. Выбор не двигает камеру, сохраняется при 2D/3D и сбрасывается при смене плана/профиля/маршрута.
- Анимация обновляется 10 раз в секунду, прекращается при размонтировании; `prefers-reduced-motion` оставляет статические стрелки. Стрелки и сплошная обводка не добавляются к приближённым линиям без дорожной геометрии. Offline SVG сохраняет прежнее поведение.
- Ручная приёмка: Восток / optimized / standard → выбрать участок кликом и через список на наложении → проверить направление стрелок → снять выделение → 3D → replan/reset. Встроенный браузер недоступен; визуальная проверка здесь не выполнена.

Car leg с `routing_source=road` показывает provider GeoJSON. Fallback leg всегда подписан `Расчётный путь`, не автомобильный маршрут по дорогам. При `routing_unavailable` сценарий показывает: `Дорожный сервис временно недоступен. Перепланирование не выполнено.` и сохраняет event/profile для Retry.

Start the backend first:

```powershell
.\scripts\start-api.ps1
```

Then start the frontend:

```powershell
cd .\frontend
npm.cmd run dev
```

Open `http://localhost:5173`. `VITE_API_BASE_URL` is configured in `.env.example`. После замены Leaflet выполните `npm.cmd install`. UI-003B.2 использует npm `maplibre-gl` (lockfile: 5.24.0) и online OpenFreeMap Liberty style `https://tiles.openfreemap.org/styles/liberty`. Подложка не требует API-ключа и содержит OSM-based улицы, кварталы, подписи и building layers. Backend, API и вычисления остаются офлайн. Нет CDN-скриптов, ключей, OSRM, геокодирования или live-пробок.

UI-002 adds the API-backed baseline/optimized toggle, comparison strip (same territory and traffic scenario only), active route list, selectable route timeline and the unassigned diagnostic list. Kilometres remain visually neutral: optimization first maximizes coverage, then reduces active engineers and only then minimizes distance.
## REPLAN-001 simulation

For East the dispatcher exposes the explicit `Срочная авария · 14:30` simulation. A successful result shows `Аварийный резерв активирован`; reset reloads the canonical optimized plan, so the synthetic standby route disappears. This is a synthetic event simulation, not live monitoring.

Request explanations are available on demand from the dedicated endpoint; they are not prefetched for all requests.

## UI-003B: карта и компоновка

- Header 56px; карта занимает всю оставшуюся высоту viewport. Белые floating controls/KPI слева, список маршрутов шириной 282px справа, с внутренней прокруткой. Drawer открывается поверх карты, не сдвигает сетку; body не прокручивается. Первый непустой маршрут выбирается автоматически, drawer по умолчанию закрыт.
- `2D`: pitch/bearing 0. `3D`: плавно 60°/−20° без изменения фильтров, выбранного маршрута или replan. OpenFreeMap Liberty содержит native `building-3d` (`openmaptiles/building`), поэтому UI скрывает этот layer в 2D и включает в 3D. Если будущая версия style не содержит extrusion, сохраняется только наклон камеры с честной подписью. Другие источники не подключались.
- После изменения API-геометрии/плана/profile bounds включают офисы, видимые заявки и концы отображаемых legs. Выбранные legs 7px с белым outline 11px; прочие 2px с opacity 0.28. Офис чёрно-жёлтый, выбранные stops нумеруются, неназначенные coral, `≈` и warning видны в деталях/легенде. Движение инженерa в реальном времени не моделируется.
- При ошибке WebGL/style/tiles либо незавершённой инициализации за 8 секунд MapLibre удаляется. Полноценная светлая SVG-схема остаётся; 3D disabled с подписью. Схема поддерживает drag, zoom, popup и выбор маршрута, не использует изображения/тайлы/шрифты из сети. Уже во время загрузки подложки отображается схема. Никакой предварительной выгрузки тайлов на диск.
- Используются только API-координаты. Между офисом и первым визитом есть leg; возврата нет. Отсутствующая координата разрывает линию, а не заменяется городом или соседней заявкой. Карта не выполняет snapping.

### Цвета сценария

`scene.ts` вычисляет FNV-1a 32-bit от `${traffic_profile}:${engineer_id}:${stop_sequence}`; unsigned hash modulo 100 определяет visual bucket. Seed/случайность/текущие часы не используются.

| Профиль | Зелёный «свободно» | Жёлтый «умеренно» | Красный «пик» |
|---|---|---|---|
| standard | bucket 0–81 | 82–99 | — |
| moderate | 0–37 | 38–87 | 88–99 |
| peak | 0–9 | 10–47 | 48–99 |

Это распределение визуальных классов, а не гарантированные доли на коротком маршруте. Hover показывает номер leg и **существующие API** `travel_minutes`/`distance_km`, класс и «Модельный сценарий, не данные о текущих пробках». Легенда постоянно содержит «Не live-пробки». Backend traffic factors 1.00/1.15/1.35, километры, нормативы и длительности не меняются.

### Replan и открытое ограничение

После применения KPI берутся из `replanned_plan.summary`, assignments и порядок — из его routes/stops, маркеры статусов — из `committed_stops`/diff. Reserve показан отдельным incident-only ресурсом, reset возвращает canonical view. Timeline отображает время явно в Europe/Moscow.

**UI-003B пока blocked по геометрии urgent.** `POST /replan` возвращает urgent payload без coordinates и без `location_source_request_id`; `/requests` содержит только canonical заявки. Геокэш имеет наследуемую точку, но читать его напрямую из frontend или угадывать по адресу нельзя. Поэтому urgent показывается в timeline, офис резерва — на карте, а неизвестный leg не рисуется, с предупреждением «Нет координат в API». Для завершения требования «urgent-точка и линия на карте» нужна отдельная команда на публичную API-проекцию существующей геометрии. Текущий этап API не меняет.

### Проверки

`npm.cmd install`, lint, typecheck, Vitest **26 passed**, production build — успешно. MapLibre mock не создаёт WebGL/сетевые запросы; проверяются camera modes, условные extrusions, fallback с реальной geometry fixture, bounds, все профили цветов, no-return, отсутствие выдуманной urgent-точки, default/changed route, reserve/reset и прежние explanation-тесты. Build предупреждает о lazy MapLibre chunk ~1.06 MB (gzip ~285 KB); библиотека выделена dynamic import, warning не скрывается.

**Реальный browser visual QA не выполнен**: browser skill вернул `Browser is not available: iab`. Размер/читаемость/работа WebGL не считаются подтверждёнными unit-тестами. Ручной [checklist 1366×768](manual_qa_checklist.md) обязателен перед визуальной приёмкой.

## UI-003B.1: demo-first correction

Первый экран открывается как `east / optimized / standard / 2D`; первый непустой маршрут выбран, его drawer закрыт. Fit включает только офис и API-stops выбранного route, поэтому остальные 205 точек не уменьшают его до нечитаемого масштаба. Выбранные legs — 7px с 11px outline; прочие — 1.5px/opacity 0.20. Context markers 8px, stop markers 20px, office 28px — ни один marker не больше 32px.

Одинаковые координаты не изменяются в данных и route lines. Для markers `scene.ts` группирует позиции, округлённые до 4 знаков, сортирует по stable ID и добавляет display-only offset по golden angle 137.508° с шагом 0.00018°. Повторный render даёт то же расположение.

В `all` без route selection карта показывает три группы точек (East yellow, Southeast blue, Southcenter violet) и три офиса, без ложного «общего маршрута». Route panel группирует строки по office territory. Выбор route показывает его линии и меняет bounds на его office/stops, не подменяя territory API и бизнес-данные.

### Почему мог включаться fallback

Аудит нашёл ошибку: прежний `map.on("error", fallback)` реагировал на любую ошибку ресурса, в том числе после успешного `load`. Теперь post-load resource error лишь даёт безопасное console warning и сохраняет карту. Fallback включается только с классификацией:

- `style_or_cors_error` — error до события style `load`;
- `style_load_timeout` — нет `load` за 12 секунд;
- `map_initialization_error` / `maplibre_module_error`;
- `application_layer_error`;
- `webgl_context_lost`.

UI не показывает traceback. В fallback рядом с disabled 3D виден текст «3D доступен при загрузке онлайн-карты». Probe из этой среды получил HTTP 200 и 77,224 bytes от разрешённого style URL, но browser preview недоступен: online rendering и camera tilt этим не подтверждены.

UI-003B.1 gate: ESLint passed, TypeScript passed, Vitest **30 passed**, Vite build passed. MapLibre dynamic chunk остаётся около 1.06 MB (gzip 285 KB), Vite size warning не скрывается.

### Ручная проверка 1366×768

1. Открыть DevTools Console, reload. Убедиться, что первый экран East/optimized/standard/2D и выбранная линия читаема.
2. Если badge `Офлайн-схема`, записать только значение `[RouteFlow map] fallback: ...` и проверить Network для `tiles.openfreemap.org`; не подключать другой provider.
3. Если `OpenFreeMap`, проверить улицы, кварталы и подписи, затем нажать 3D: pitch и здания должны появиться, route selection сохраниться.
4. Сравнить standard/moderate/peak; выбранные legs остаются зелёными/жёлтыми/красными, легенда говорит «Модельная оценка, не текущие пробки».
5. Выбрать «Все»: route lines отсутствуют до выбора строки; видны три группы. Выбрать route другой территории — map focus должен перейти к его офису/stops.

## UI-003B.2: OpenFreeMap Liberty

Тестовая `demotiles.maplibre.org` подложка полностью заменена на `https://tiles.openfreemap.org/styles/liberty`. Проверка endpoint из среды: HTTP 200, JSON 43,079 bytes, sources `ne2_shaded` и `openmaptiles`, 111 layers, включая 67 transportation/road layers, 25 symbol layers и native `building-3d` fill-extrusion. Это подтверждает контракт style, но не является visual QA в браузере.

После события MapLibre `load` UI показывает `OpenFreeMap`, не `Офлайн-схема`. Post-load resource/tile error не уничтожает карту. До-load CORS/style error, timeout, WebGL loss и initialization failure сохраняют локальный SVG fallback без сетевых запросов. В 3D используется существующий `building-3d`; при отсутствии native extrusion `routeflow-buildings` создаётся только из подтверждённого `openmaptiles/building` source-layer.

Атрибуция: `© OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors`. Легенда фиксирует: `Линия показывает последовательность визитов; не навигация по улицам.` Traffic overlay остаётся модельным и не изменяет route geometry или расчёты.

Проверки UI-003B.2: frontend lint/typecheck passed, Vitest **31 passed**, production build passed. Browser preview недоступен, поэтому фактическая видимость улиц, WebGL-render и 3D buildings требуют ручной проверки.

## Диагностика online-подложки

В development-режиме control card показывает `Подложка: loading | online | offline` и короткую `Причина`. Строка скрыта в production build. Возможные коды: `style_timeout`, `style_load_failed`, `webgl_unavailable`, `map_init_failed`, `container_unavailable`. Пользовательский UI не выводит raw error или stack trace; console пишет ровно один `[RouteFlow map] fallback: <reason>` при фактическом fallback.

Проверены все ресурсы, необходимые для начального viewport Москвы: style, sprite JSON/PNG, glyph PBF (`Noto Sans Regular`), TileJSON, vector tile `z10/618/320` и Natural Earth raster tile. Каждый получил HTTP 200, ожидаемый Content-Type и `Access-Control-Allow-Origin: *`; в Vite/index.html CSP отсутствует. Следовательно, style server chain из development-среды доступна.

Исправлен lifecycle defect: прежде любой MapLibre `error` до `load` сразу включал fallback, хотя sprite/glyph/tile error может быть recoverable. Теперь такой event лишь помечает pending `style_load_failed`; fallback включается через 30 секунд только если `map.load` так и не наступил. Последующий `load` очищает причину и переводит карту в online. Проверки покрывают `loading → online` после ранней recoverable ошибки, timeout classification и zero-size container.

Причина fallback на присланном скриншоте пока не доказана: in-app browser недоступен, а в скриншоте нет dev diagnostic/console code. После локального reload нужно прочитать строку `Причина` либо одну console запись. `style_load_failed` означает отсутствие `load` после ранней ошибки; `style_timeout` — отсутствие ошибок и `load` 30 секунд; `container_unavailable` — нулевой размер host; `webgl_unavailable` — потеря WebGL. Только этот код позволит отличить внешний browser restriction от lifecycle regression.

## Дорожная геометрия выбранного маршрута

Открытие drawer запускает один `POST .../road-geometry`, только если хотя бы у одного участка нет дорожной формы. Backend передаёт всю фиксированную последовательность точек одним запросом OSRM и возвращает отдельную GeoJSON-линию для каждого участка. Повторное открытие использует process/frontend cache. Это визуальная гидратация: порядок заявок, arrival/service, расстояния, traffic profile и KPI опубликованного плана не пересчитываются.

Для инженера без автомобиля автомобильная дорожная линия служит только визуальным путём между точками; его расчётное время остаётся приближённым. Drawer показывает loading, готовность или контролируемую ошибку с Retry. Сплошная линия означает `cache`/`on_demand`, пунктир — `Дорожная геометрия недоступна`. Public demo OSRM используется только этим явным интерактивным действием в локальном launcher; production должен задавать self-hosted `ROUTEFLOW_ROUTE_GEOMETRY_URL`.
## Account entry and vector identity

The Liquid Glass material is centralized in `styles/glass.css`: tinted panels with background blur, rim highlights and consistent controls. Dense route lists retain a stronger tint for contrast over the map. Browsers without backdrop-filter receive opaque panels; reduced transparency also uses opaque material. The supplied `BeelineLogo.tsx` provides the unchanged vector geometry via the `BeeLogo` adapter.

After authentication/session restore, the workspace mounts immediately beneath a decorative, pointer-transparent 1.1-second logo reveal. Header and side panels enter once, without animating the MapLibre canvas or imposing an artificial API wait. Reduced-motion hides the curtain entirely. Visual QA remains pending: verify login, map panels and dialogs at 1366×768 in a real browser.

`AuthGate` restores the signed backend session before rendering the dispatcher workspace. Without a valid session it shows a responsive login screen with loading, invalid-credentials and submit states. A `401` from a protected API endpoint returns the user to that screen; the header account menu shows the current role and provides logout.

`BeeLogo.tsx` is a reusable code-native SVG composition rather than a raster asset or external download. The same mark is used in startup, login and the application header. Its bands and highlight animate independently, while `prefers-reduced-motion` disables nonessential motion.

Explanations, plans and route data are not prefetched on the login screen. Auth requests use `credentials: include`; keep the UI and API on the same host name (`localhost` in the provided frontend example) so local HTTP cookies behave consistently.


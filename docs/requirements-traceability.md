# Требования и проверка

Краткая карта реализации; зелёные тесты не означают доказанную глобальную оптимальность или полное закрытие replan. Подробные незакрытые пункты — в [аудите](qa-audit-2026-09-29.md).

| Требование | Реализация / подтверждение |
| --- | --- |
| Только synthetic allowlist, CP1251, 205 заявок | backend/tests/test_csv_loader.py, test_normalization.py |
| Нормативы и детерминированное обогащение | test_normatives.py, test_enrichment.py |
| Навыки, транспорт, окна, смены, no-return | test_baseline.py, test_optimizer.py |
| Исходный порядок baseline | test_baseline.py |
| Приоритет coverage → engineers → distance | test_optimizer.py; ограничение search budget описано в аудите |
| Общие метрики и verified diagnostics | test_metrics_diagnostics.py |
| Traffic profiles, офлайн fallback, road cache | test_traffic.py, test_routing.py, test_road_cache_repository.py |
| События и committed prefix | test_replan.py, test_replan_closure.py; mutable-suffix VRPTW и cancellation требуют доработки |
| API, сессия, объяснения | test_api.py, test_auth.py, test_explanations.py |
| Карта, выбор маршрута, replan/reset, explanations | frontend/src: Vitest; визуальная приёмка по manual_qa_checklist.md |

Все указанные backend-файлы находятся в `backend/tests/`. Перед показом выполните полный `scripts/smoke.ps1` и ручной checklist.

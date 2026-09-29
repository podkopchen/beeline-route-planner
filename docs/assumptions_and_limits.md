# Допущения и ограничения

## Routing

Для новой реальной заявки CRM должна передать валидные координаты. Геокодинг в RouteFlow не выполняется. Тёплый road cache — только ускоритель; road-required deployment не выдаёт прямую линию за автомобильный маршрут при недоступности routing service.

- Данные и события synthetic; control CSV исключены allowlist-ом.
- Координаты могут быть approximate/street/proxy и не всегда являются точными адресами.
- Traffic profiles — офлайн-сценарии, не live-пробки.
- Runtime не вызывает геокодеры или внешние routing APIs.
- Urgent duration из NORM-001: 80 минут для аварийной network repair работы.
- `reserve-east-emergency-01` — documented synthetic operational assumption только для urgent event; canonical 35 engineers и KPI не меняются.
- `final_plan_insertion_infeasible` означает fixed-plan insertion limit, а не глобальную невозможность.
## Authentication

- Текущий аккаунт — один локальный dispatcher для демонстрации, заданный переменными окружения backend.
- Это настоящая серверная проверка и подписанная `HttpOnly` session cookie, но не production IAM.
- Регистрация, восстановление пароля, БД пользователей, роли нескольких уровней, MFA, SSO и аудит входов пока отсутствуют.
- Секрет launcher создаётся заново при старте процесса: перезапуск API завершает активные сессии.
- Для production обязательны HTTPS, `Secure` cookie, защищённый постоянный secret и корпоративный identity provider.


# Evidence: Календарь и временная модель

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

ProductionCalendar содержит полный уникальный месяц, kind working/off/short, source/fetched_at/verified/used_saved. Только matching verified snapshot является fallback; weekday approximation остаётся unverified диагностикой. Утро/вечер/ночь используют МСК, только вечер пересекает дату; R начинается09 местного времени. Индивидуальный R ICS содержит часы и начало без DTEND/DURATION.

Продуктовый контракт сохранён в decisions.md изменения004. Перед реализацией были spec/plan/tasks/traceability. Реальные регрессии выявили и закрыли shared approvals order, active-month dependency gaps, malformed changelog, per-period pins loss, What-if CalendarError, unavailable fairness pool и packaged smoke context.

Независимое ревью: domain_python_review (Python/domain), integration_code_review (UI/project integration), api_security_delivery_review (API/security/delivery). Исполнители не коммитили; root независимо просмотрел fixes, ревьюеры повторно проверили root fixes. Новых CRITICAL/HIGH в проверенной области не осталось. Исторический исход планирования выше сохранён.

Общие команды, runtime результаты и ограничения: [evidence поставки](../011-delivery-assurance/evidence.md). Окончательные gates будут добавлены после завершения последнего прогона; текущий статус in-progress.

## 2026-10-11T00:37:32+03:00 — завершение локальной реализации

Критерии проверены связанными тестами: общий прогон750passed, coverage85.73%, браузер7passed, независимые review fixes закрыты. Реальные команды и границы доказательств находятся в [общем evidence](../011-delivery-assurance/evidence.md). Задачи T001–T005 закрыты; статус complete относится к реализации этих требований, не к публикации релиза.

Смысловое SDD-ревью исправило привязку TIME-001/002: полный/проверенный/saved
календарь относится к TIME-001, общая арифметика типов дат и часов — к TIME-002.
Структурный gate до этого был зелёным; сама ошибка была в смысле mapping, не в коде.

## 2026-10-11 — миграция к строгому SDD и явная приёмка

Область `files` восстановлена из плана и реальных файлов. Это актуализация
живого контракта, а не утверждение о ретроспективном прохождении нового gate.

| ID | Проверяющие тесты | Evidence |
|---|---|---|
| TIME-001 | `tests/unit/test_calendar_model.py::test_calendar_preserves_working_saturday_and_short_day`, `tests/unit/test_calendar_model.py::test_calendar_rejects_unknown_codes`, `tests/unit/test_calendar_model.py::test_calendar_requires_complete_unique_month`, `tests/unit/test_calendar_model.py::test_calendar_uses_only_verified_saved_requested_period`, `tests/unit/test_calendar_model.py::test_wrong_saved_period_does_not_replace_calendar` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| TIME-002 | `tests/unit/test_calendar_model.py::test_calendar_preserves_working_saturday_and_short_day`, `tests/unit/test_hour_consumers.py`, `tests/unit/test_workload.py::test_assignment_hours_share_short_and_individual_workday_model` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| TIME-003 | `tests/unit/test_export_time_model.py`, `tests/unit/test_ics_per_employee.py`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

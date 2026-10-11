# Evidence: Достоверная история между месяцами

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

Перенос хранит ID/имя, as_of, source и раздельные рабочие/одинаковые/выходные серии; compute_carry_over учитывает initial_history. XLS содержит hidden metadata chunked JSON и индивидуальные часы; importer пересчитывает реальные ячейки с initial history, отвергает неизвестные и пустые смены. Range сохраняет matching calendar snapshots, переносит только ready и останавливается на первом diagnostic.

Продуктовый контракт сохранён в decisions.md изменения004. Перед реализацией были spec/plan/tasks/traceability. Реальные регрессии выявили и закрыли shared approvals order, active-month dependency gaps, malformed changelog, per-period pins loss, What-if CalendarError, unavailable fairness pool и packaged smoke context.

Независимое ревью: domain_python_review (Python/domain), integration_code_review (UI/project integration), api_security_delivery_review (API/security/delivery). Исполнители не коммитили; root независимо просмотрел fixes, ревьюеры повторно проверили root fixes. Новых CRITICAL/HIGH в проверенной области не осталось. Исторический исход планирования выше сохранён.

Общие команды, runtime результаты и ограничения: [evidence поставки](../011-delivery-assurance/evidence.md). Окончательные gates будут добавлены после завершения последнего прогона; текущий статус in-progress.

## 2026-10-11T00:37:32+03:00 — завершение локальной реализации

Критерии проверены связанными тестами: общий прогон750passed, coverage85.73%, браузер7passed, независимые review fixes закрыты. Реальные команды и границы доказательств находятся в [общем evidence](../011-delivery-assurance/evidence.md). Задачи T001–T005 закрыты; статус complete относится к реализации этих требований, не к публикации релиза.

## 2026-10-11 — миграция к строгому SDD и явная приёмка

Область `files` восстановлена из плана и реальных файлов. Это актуализация
живого контракта, а не утверждение о ретроспективном прохождении нового gate.

| ID | Проверяющие тесты | Evidence |
|---|---|---|
| HIST-001 | `tests/unit/test_planning_rules.py::test_previous_month_evening_and_stale_history`, `tests/unit/test_planning_rules.py::test_streak_approval_is_date_employee_value_specific_and_never_allows_eight`, `tests/unit/test_solver.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| HIST-002 | `tests/unit/test_ui_workflow.py::test_manual_history_requires_explicit_known_or_new_employee`, `tests/unit/test_project.py::test_standalone_month_with_verified_external_history_is_allowed`, `tests/unit/test_planning_rules.py::test_validator_rejects_forged_ready_and_missing_calendar_history` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| HIST-003 | `tests/unit/test_history.py`, `tests/unit/test_xls_import.py`, `tests/integration/test_xls_roundtrip.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| HIST-004 | `tests/unit/test_multimonth.py::test_range_keeps_ready_month_and_stops_on_first_diagnostic`, `tests/integration/test_multimonth.py`, `tests/unit/test_project.py::test_load_reconstructs_entire_active_month_dependency_chain` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

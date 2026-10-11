# Evidence: Версии графика и файл проекта

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

project.py реализует формат1, неизменяемые snapshots revisions, per-period active map, parent/dependency references, manual pinning обеих сторон замены и свежий export guard. Импорт проверяет ID/периоды/DAG и отсутствие связанного active predecessor, TypeAdapter(ChangeLog), затем назначения/перенос всей активной цепочки. Saved ready/cache не доверяются. Current snapshot возвращается как detached copy; изменение предыдущего месяца инвалидирует будущие версии.

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
| REV-001 | `tests/unit/test_project.py`, `tests/unit/test_ui_workflow.py::test_revision_comparison_displays_changed_individual_workday_hours`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| REV-002 | `tests/unit/test_project.py::test_project_round_trip_preserves_revisions_and_hours`, `tests/unit/test_project.py::test_invalid_saved_changelog_is_rejected_before_replacing_project`, `tests/unit/test_project.py::test_load_reconstructs_entire_active_month_dependency_chain`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| REV-003 | `tests/unit/test_project.py::test_edit_pins_both_changed_participants`, `tests/unit/test_ui_workflow.py::test_ui_range_preserves_configuration_and_manual_pins_of_each_period`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| REV-004 | `tests/contract/test_revision_api.py::test_forged_ready_schedule_cannot_be_exported`, `tests/unit/test_cli_project.py`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

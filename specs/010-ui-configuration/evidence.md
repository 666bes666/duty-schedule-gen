# Evidence: Составление графика в интерфейсе

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

app.py делегирует оркестрацию ui/components.py; типизированные YAML/table adapters проверяют вход до изменения state. UI хранит ScheduleProject и отображает одну текущую версию, sickness/norm/history/approval/R controls, pins/unpin, save/open и настоящий range. Каждый месяц повторного range берёт свой Config и свежий carry. What-if использует API patch schema, ловит CalendarError; diff показывает old/new R hours; legacy sorting/bulk/charts/cost/ICS остаются.

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
| UIC-001 | `tests/unit/test_ui_workflow.py::test_yaml_roundtrip_preserves_all_typed_fields`, `tests/unit/test_ui_workflow.py::test_yaml_import_is_atomic_for_invalid_input`, `tests/unit/test_ui_workflow.py::test_empty_team_is_rejected_instead_of_demo_substitution` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| UIC-002 | `tests/unit/test_ui_workflow.py`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| UIC-003 | `tests/unit/test_ui_workflow.py::test_real_streamlit_project_edit_check_and_reopen`, `tests/unit/test_ui_workflow.py::test_revision_comparison_displays_changed_individual_workday_hours`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| UIC-004 | `tests/unit/test_ui_workflow.py::test_whatif_ui_uses_the_api_patch_fields`, `tests/unit/test_ui_workflow.py::test_whatif_calendar_mismatch_is_reported_without_crashing_application`, `tests/unit/test_ui_workflow.py::test_ui_range_keeps_first_ready_month_and_stops_at_diagnostic`, `tests/integration/test_whatif_endpoint.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

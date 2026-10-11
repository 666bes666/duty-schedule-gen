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

## 2026-10-11 — уточнение контракта после продуктового интервью 013

UIC-001 дополнен сохранностью допустимых имён/полной исходной истории при unchanged UI round-trip (DATA-001/002). UIC-003 требует правдивого объяснения оптимизации и подписанного окна метрик (DATA-005/QUALITY-003). UIC-004 проверяет одинаковые top-level/nested patch пути UI/API, исключая ложный успех опечатки (DATA-003). Основные правки происходят в приложении; XLS/PDF — выдача, импорт старой истории сохраняется.

Новые критерии НЕ реализованы. Прежние PASS выше сохраняются как история
проверки прежних требований; они не доказывают устранение PLOG или выполнение
новых сценариев. Новые test selectors запланированы, исходники/тесты не изменены.
Status возвращён в planned. Анализ и gates документов: evidence013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **UIC-001**: приёмка проверена тестами `tests/unit/test_ui_workflow.py::test_yaml_roundtrip_preserves_all_typed_fields`, `tests/unit/test_ui_workflow.py::test_yaml_import_is_atomic_for_invalid_input`, `tests/unit/test_ui_workflow.py::test_empty_team_is_rejected_instead_of_demo_substitution`, `tests/unit/test_product_integrity.py::test_unchanged_history_preserves_counters_and_source`, `tests/unit/test_product_integrity.py::test_employee_identity_roundtrips_names_and_rejects_blank`.
- **UIC-002**: приёмка проверена тестами `tests/unit/test_ui_workflow.py`, `tests/ui/test_project_journey.py`.
- **UIC-003**: приёмка проверена тестами `tests/unit/test_ui_workflow.py::test_real_streamlit_project_edit_check_and_reopen`, `tests/unit/test_ui_workflow.py::test_revision_comparison_displays_changed_individual_workday_hours`, `tests/ui/test_project_journey.py`, `tests/ui/test_product_recovery.py::test_unavailable_log_is_not_reported_as_no_changes`.
- **UIC-004**: приёмка проверена тестами `tests/unit/test_ui_workflow.py::test_whatif_ui_uses_the_api_patch_fields`, `tests/unit/test_ui_workflow.py::test_whatif_calendar_mismatch_is_reported_without_crashing_application`, `tests/unit/test_ui_workflow.py::test_ui_range_keeps_first_ready_month_and_stops_at_diagnostic`, `tests/integration/test_whatif_endpoint.py`, `tests/contract/test_product_inputs.py::test_unknown_nested_patch_is_422_without_search`.
- **UIC-005**: приёмка проверена тестами `tests/ui/test_first_month_journey.py::test_preflight_explains_unknown_history_and_pin_conflict`, `tests/ui/test_first_month_journey.py::test_first_month_without_all_cell_pins_and_technical_operations`.
- **UIC-006**: приёмка проверена тестами `tests/ui/test_product_recovery.py::test_browser_reload_restores_current_project_and_hours`, `tests/unit/test_ui_autosave.py::test_failed_and_corrupt_storage_preserve_valid_snapshot`, `tests/ui/test_product_recovery.py::test_two_tabs_do_not_silently_overwrite_newer_revision`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

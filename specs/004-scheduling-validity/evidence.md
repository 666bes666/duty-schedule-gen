# Evidence: Проверяемый результат планирования

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

scheduler/rules.py задаёт единые роли, доступность, отдых, серию и подтверждения; scheduler/validation.py независимо пересчитывает календарь, нормы, назначения, историю и перенос. Greedy и CP-SAT возвращают Schedule со status/diagnostics/search_status. Подтверждения фильтруются по employee/date/value, не зависят от порядка и не уменьшают обычный лимит. Timeout/exhaustion проверяются отдельными реальными runtime-регрессиями.

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
| VALID-001 | `tests/unit/test_planning_rules.py::test_all_states_checked_and_absences_not_fabricated`, `tests/unit/test_planning_rules.py::test_engines_return_ready_only_with_exact_hours_and_shared_rules`, `tests/unit/test_planning_rules.py::test_empty_night_pool_returns_diagnostic_not_false_success`, `tests/integration/test_hypothesis.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| VALID-002 | `tests/unit/test_planning_rules.py::test_unavailable_sick_leave_and_workday_on_off_are_hard`, `tests/unit/test_planning_rules.py::test_role_limits_are_preserved_by_both_engines`, `tests/unit/test_planning_rules.py::test_previous_month_evening_and_stale_history` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| VALID-003 | `tests/unit/test_planning_rules.py::test_streak_approval_is_date_employee_value_specific_and_never_allows_eight`, `tests/unit/test_planning_rules.py::test_solver_streak_approvals_are_order_independent`, `tests/unit/test_planning_rules.py::test_solver_cannot_apply_unmatched_streak_approval`, `tests/unit/test_planning_rules.py::test_solver_streak_approval_cannot_reduce_normal_limit` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| VALID-004 | `tests/unit/test_planning_rules.py::test_validator_rejects_forged_ready_and_missing_calendar_history`, `tests/unit/test_search_outcomes.py`, `tests/contract/test_revision_api.py::test_plan_returns_diagnostics_but_legacy_generate_rejects_them` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

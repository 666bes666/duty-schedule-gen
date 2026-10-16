# Evidence: Нормы часов и качество графика

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

workload.py является общей арифметикой 8/7/individual hours и selected monthly target. Отсутствия вычитаются union рабочих дат; full choice относится к employee/month. Stats, costs, XLS, UI, engines и validator используют эту модель. Качество фиксировано лексикографически. CP, postprocess и What-if summary используют общий eligible_duty_names для пропорционального баланса среди реально доступных сотрудников.

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
| HOURS-001 | `tests/unit/test_workload.py::test_norm_deducts_union_of_working_absences_only`, `tests/unit/test_hour_consumers.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| HOURS-002 | `tests/unit/test_workload.py::test_full_norm_choice_is_period_specific`, `tests/unit/test_planning_rules.py::test_full_norm_after_short_absence_proposes_individual_r_confirmation` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| HOURS-003 | `tests/unit/test_planning_rules.py::test_individual_workday_requires_exact_confirmation`, `tests/integration/test_pipeline_hour_compatibility.py::test_legacy_pipeline_preserves_short_day_and_confirmed_individual_hours`, `tests/ui/test_project_journey.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| HOURS-004 | `tests/unit/test_planning_rules.py::test_legacy_priority_does_not_change_agreed_greedy_quality_order`, `tests/unit/test_planning_rules.py::test_off_duty_quality_balances_only_available_employees`, `tests/unit/test_planning_rules.py::test_solver_off_duty_balance_ignores_weekday_only_duty_role`, `tests/unit/test_whatif_service.py::test_quality_is_proportional_to_selected_hours`, `tests/unit/test_whatif_service.py::test_summary_off_duty_balance_uses_available_pool` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

## 2026-10-11 — уточнение контракта после продуктового интервью 013

HOURS-004 явно изменён по ответу владельца: окно баланса теперь текущий и предыдущий месяц, а не только месяц расчёта. При первом построении порядок мягких целей сохраняется; в repair до этих целей минимизируются изменённые ячейки (016). Нормы/доступность учитываются для каждого подходящего пула и периода, missing history не подменяется нулём (017). HARD требования HOURS-001..003 сохранены.

Новые критерии НЕ реализованы. Прежние PASS выше сохраняются как история
проверки прежних требований; они не доказывают устранение PLOG или выполнение
новых сценариев. Новые test selectors запланированы, исходники/тесты не изменены.
Status возвращён в planned. Анализ и gates документов: evidence013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **HOURS-001**: приёмка проверена тестами `tests/unit/test_workload.py::test_norm_deducts_union_of_working_absences_only`, `tests/unit/test_hour_consumers.py`.
- **HOURS-002**: приёмка проверена тестами `tests/unit/test_workload.py::test_full_norm_choice_is_period_specific`, `tests/unit/test_planning_rules.py::test_full_norm_after_short_absence_proposes_individual_r_confirmation`.
- **HOURS-003**: приёмка проверена тестами `tests/unit/test_planning_rules.py::test_individual_workday_requires_exact_confirmation`, `tests/integration/test_pipeline_hour_compatibility.py::test_legacy_pipeline_preserves_short_day_and_confirmed_individual_hours`, `tests/ui/test_project_journey.py`.
- **HOURS-004**: приёмка проверена тестами `tests/unit/test_planning_rules.py::test_legacy_priority_does_not_change_agreed_greedy_quality_order`, `tests/unit/test_planning_rules.py::test_off_duty_quality_balances_only_available_employees`, `tests/unit/test_planning_rules.py::test_solver_off_duty_balance_ignores_weekday_only_duty_role`, `tests/unit/test_whatif_service.py::test_quality_is_proportional_to_selected_hours`, `tests/unit/test_whatif_service.py::test_summary_off_duty_balance_uses_available_pool`, `tests/unit/test_two_month_quality.py::test_cumulative_weights_use_eligible_roles_and_selected_norm_each_period`, `tests/integration/test_two_month_quality.py::test_both_engines_use_exactly_two_months`.
- **HOURS-005**: приёмка проверена тестами `tests/unit/test_two_month_quality.py::test_month_and_boundary_streak_windows_are_distinct`, `tests/unit/test_product_integrity.py::test_optimizer_without_changelog_reports_changes_and_quality`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

## 2026-10-11 — dev delivery и закрытие контракта

Реализация: `922b0c09dfc96698e62e1db414b794f07ba11576` (`feat: deliver reliable authoring, stable repair and two-month quality`). `git push origin dev` прошёл; локальный HEAD и origin/dev совпали, рабочее дерево чистое. До коммита `check_sdd.py --staged` и hooks прошли; перед push `check_sdd.py --base HEAD~1` и project_context --check прошли. Все критерии/задачи текущего контракта проверены; status complete означает реализацию и dev delivery.

[PR66 dev→test](https://github.com/666bes666/duty-schedule-gen/pull/66) обновляется автоматически новым dev head. CI на новом SHA запущен; test/main promotion не выполнен и требует зелёного CI и одного required approving review. Это ограничение доставки релиза, а не непроверенное поведение закрытого контракта.

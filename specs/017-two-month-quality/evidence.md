# Evidence 017

## 2026-10-11 — согласованное окно качества

QUALITY-001/002/003 основаны на выборе владельца: текущий и предыдущий месяц.
В текущем runtime баланс месячный; boundary stats и действие preferences
различаются между потребителями (PLOG-06/07). Новые model/objectives/tests
не реализованы. Status planned. Анализ/gates этих документов — evidence 013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **QUALITY-001**: приёмка проверена тестами `tests/integration/test_two_month_quality.py::test_both_engines_use_exactly_two_months`, `tests/integration/test_two_month_quality.py::test_changed_role_receives_only_eligible_period_weight`, `tests/unit/test_two_month_quality.py::test_cumulative_weights_use_eligible_roles_and_selected_norm_each_period`, `tests/unit/test_two_month_quality.py::test_new_and_departed_employee_do_not_invent_previous_counts`.
- **QUALITY-002**: приёмка проверена тестами `tests/unit/test_two_month_quality.py::test_missing_and_stale_history_are_not_zero`, `tests/unit/test_two_month_quality.py::test_previous_active_revision_changes_quality_source`, `tests/unit/test_two_month_quality.py::test_project_invalidates_old_quality_source_and_reload`, `tests/unit/test_two_month_quality.py::test_rebinding_updated_previous_revision_reenables_quality`, `tests/unit/test_two_month_quality.py::test_whatif_preserves_trusted_quality_context`, `tests/unit/test_two_month_quality.py::test_year_boundary_checks_adjacent_period_without_fabricating_history`, `tests/unit/test_two_month_quality.py::test_config_save_cannot_resurrect_stale_quality_source`.
- **QUALITY-003**: приёмка проверена тестами `tests/contract/test_quality_context.py::test_standalone_api_reports_month_only_quality`, `tests/ui/test_quality_journey.py::test_summary_and_exports_show_same_quality_window`, `tests/unit/test_two_month_quality.py::test_month_and_boundary_streak_windows_are_distinct`, `tests/unit/test_two_month_quality.py::test_pdf_renderer_receives_month_and_boundary_series`, `tests/unit/test_two_month_quality.py::test_xls_external_quality_source_id_is_plain_text`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

QUALITY-001/002/003: Fraction и integer-scaled solver используют ровно два месяца; source active ID/config/days проверяется при открытии и создании версии. Missing/stale не выдаются за verified. PDF renderer тест проверяет реально переданный HTML; внешние XLS ID санитизируются как текст.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

## 2026-10-11 — dev delivery и закрытие контракта

Реализация: `922b0c09dfc96698e62e1db414b794f07ba11576` (`feat: deliver reliable authoring, stable repair and two-month quality`). `git push origin dev` прошёл; локальный HEAD и origin/dev совпали, рабочее дерево чистое. До коммита `check_sdd.py --staged` и hooks прошли; перед push `check_sdd.py --base HEAD~1` и project_context --check прошли. Все критерии/задачи текущего контракта проверены; status complete означает реализацию и dev delivery.

[PR66 dev→test](https://github.com/666bes666/duty-schedule-gen/pull/66) обновляется автоматически новым dev head. CI на новом SHA запущен; test/main promotion не выполнен и требует зелёного CI и одного required approving review. Это ограничение доставки релиза, а не непроверенное поведение закрытого контракта.

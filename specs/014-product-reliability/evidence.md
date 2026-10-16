# Evidence 014

## 2026-10-11 — контракт после аудита

DATA-001/002/003/004/005 основаны на воспроизводимых PLOG-01–05 из
[аудита 013](../013-product-logic-audit/audit.md) и его реальных probe результатах.
Реализация и новые регрессии не выполнялись; status planned, все задачи открыты.
Существующие runtime/UI tests 794/7 не доказывают устранение этих дефектов.
Анализ согласованности и scoped gates документов фиксируются в evidence 013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **DATA-001**: приёмка проверена тестами `tests/contract/test_product_inputs.py::test_blank_employee_is_rejected_before_generation`, `tests/unit/test_product_integrity.py::test_employee_identity_roundtrips_names_and_rejects_blank`, `tests/unit/test_product_integrity.py::test_xls_preserves_exact_names_and_rejects_missing_roster`, `tests/unit/test_product_integrity.py::test_cleared_editor_cell_moves_employee_to_day_off`.
- **DATA-002**: приёмка проверена тестами `tests/ui/test_product_recovery.py::test_imported_history_unchanged_save_preserves_every_employee`, `tests/unit/test_product_integrity.py::test_editing_one_history_preserves_other_complete_states`, `tests/unit/test_product_integrity.py::test_unchanged_history_preserves_counters_and_source`.
- **DATA-003**: приёмка проверена тестами `tests/contract/test_product_inputs.py::test_invalid_merged_patch_is_422_before_baseline_search`, `tests/contract/test_product_inputs.py::test_unknown_nested_patch_is_422_without_search`, `tests/unit/test_product_integrity.py::test_legacy_team_lead_migration_is_visible`, `tests/contract/test_product_inputs.py::test_unknown_previous_snapshot_fields_are_422_before_search`.
- **DATA-004**: приёмка проверена тестами `tests/contract/test_product_inputs.py::test_mismatched_calendar_is_422_without_search_or_network`, `tests/unit/test_product_integrity.py::test_cli_and_ui_reject_mismatched_calendar_atomically`, `tests/unit/test_product_integrity.py::test_cli_rejects_mismatched_calendar_with_both_periods`, `tests/unit/test_product_integrity.py::test_ui_period_change_selects_new_calendar_before_validation`, `tests/unit/test_product_integrity.py::test_ui_period_change_selects_new_calendar_before_validation`.
- **DATA-005**: приёмка проверена тестами `tests/ui/test_product_recovery.py::test_unavailable_log_is_not_reported_as_no_changes`, `tests/unit/test_product_integrity.py::test_optimizer_without_changelog_reports_changes_and_quality`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

DATA-003 намеренно меняет unknown-field/invalid merged variant response на native422 до baseline search; прежние auth/error/export контракты проверяются общими тестами. Legacy team_lead явно мигрируется с предупреждением. DATA-005 snapshot/result revision IDs не приписываются более поздней ручной правке. Malformed operation metadata отвергается атомарно.

## 2026-10-11 — окончательные локальные delivery gates

Команды выполнялись с `UV_PROJECT_ENVIRONMENT=/tmp/duty-specs-20261011` (отдельная uv environment из locked all-groups+solver); для PDF `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

- `uv run pytest tests/ -o addopts='' -q --ignore=tests/ui --cov=duty_schedule --cov-fail-under=80 --tb=short`: **849 passed, 7 warnings, 259.23s; coverage88.18%** на стабильном runtime после review fixes.
- `uv run pytest tests/ui/ -o addopts='' -q`: **18 passed, 66.34s** после последних runtime fixes.
- После добавления только двух финальных acceptance tests: `uv run pytest tests/unit/test_product_integrity.py tests/ui/test_product_recovery.py::test_unavailable_log_is_not_reported_as_no_changes -o addopts='' -q --tb=short`: **16 passed,7.30s**. Один новый unit и один новый browser test дополняют вышеуказанные прогоны; runtime после полного прогона не менялся.
- `uv run ruff check src/ tests/ scripts/`: PASS; `uv run ruff format --check src/ tests/ scripts/`:181files PASS; `uv run mypy src/ scripts/`:69files PASS.
- `uv run python scripts/project_context.py --write`, затем `--check`: PASS; `uv run python scripts/check_sdd.py --base HEAD`: PASS. Отдельно строгая проверка всех selectors через check_test(..., True): PASS.
- `uv build --wheel --out-dir /tmp/duty-specs-artifacts`; `uv pip install --target /tmp/duty-wheel-final --no-deps /tmp/duty-specs-artifacts/duty_schedule-5.0.0-py3-none-any.whl`: PASS. Fresh process импортировал установленный package, проверил autosave HTML asset, ready/proven_zero и API422 external unknown snapshot: PASS. Первые smoke probes использовали неверное имя helper/metadata key; после исправления самого probe итоговый smoke прошёл.
- `uv run pip-audit`: No known vulnerabilities found; локальный duty-schedule5.0.0 отсутствует в PyPI и аудитом зависимостей не проверяется.
- Independent Santa cycles нашли и закрыли runtime defects; лимит3циклов потребовал разрешения владельца. Владелец явно разрешил дополнительное независимое ревью и доставку. Итог semantic_review_g PASS (47targeted tests), semantic_review_h PASS (42targeted tests). Связанные fixes проверены повторно обоими ревьюерами.

Фактические ограничения: browser storage относится к тому же origin/браузеру; JSON backup остаётся переносимым. Greedy/bounded поиск не доказывает global optimum. PDF требует system libraries. GitHub test/main promotion зависит от CI и одного required approving review; локальные PASS не означают promotion. Dev delivery SHA и результат добавляются после push.

## 2026-10-11 — dev delivery и закрытие контракта

Реализация: `922b0c09dfc96698e62e1db414b794f07ba11576` (`feat: deliver reliable authoring, stable repair and two-month quality`). `git push origin dev` прошёл; локальный HEAD и origin/dev совпали, рабочее дерево чистое. До коммита `check_sdd.py --staged` и hooks прошли; перед push `check_sdd.py --base HEAD~1` и project_context --check прошли. Все критерии/задачи текущего контракта проверены; status complete означает реализацию и dev delivery.

[PR66 dev→test](https://github.com/666bes666/duty-schedule-gen/pull/66) обновляется автоматически новым dev head. CI на новом SHA запущен; test/main promotion не выполнен и требует зелёного CI и одного required approving review. Это ограничение доставки релиза, а не непроверенное поведение закрытого контракта.

## 2026-10-11 — итог runtime/platform после переносимого PDF contract test

Полный локальный повтор:850passed,coverage88.20%; native PDF/security+quality41passed. Runtime неизменен; единственная тестовая правка изолирует renderer от DLL. Dev62cbecc; CI Dev/CI Test/обаSDD SUCCESS на этомSHA, Windows3.12/3.13 подтверждены. [Точные результаты и сохранённый исход Windows failure](../017-two-month-quality/evidence.md).

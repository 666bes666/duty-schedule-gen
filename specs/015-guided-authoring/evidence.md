# Evidence 015

## 2026-10-11 — согласованные требования

FLOW-001/004: владелец выбрал подготовку и первый расчёт как приоритет.
FLOW-002/003: владелец выбрал восстановление в том же браузере и резервный JSON.
Excel/PDF — выдача; серверное хранение не согласовано. Runtime пока теряет
нескачанный проект после reload (PLOG-09). Новые тесты/bridge не реализованы.
Status planned; все задачи открыты. Проверки документов — evidence 013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **FLOW-001**: приёмка проверена тестами `tests/ui/test_first_month_journey.py::test_preflight_explains_unknown_history_and_pin_conflict`.
- **FLOW-002**: приёмка проверена тестами `tests/ui/test_product_recovery.py::test_browser_reload_restores_current_project_and_hours`, `tests/ui/test_product_recovery.py::test_opening_existing_other_project_updates_last_pointer`.
- **FLOW-003**: приёмка проверена тестами `tests/ui/test_product_recovery.py::test_corrupt_record_preserves_last_valid_copy`, `tests/ui/test_product_recovery.py::test_two_tabs_do_not_silently_overwrite_newer_revision`, `tests/ui/test_product_recovery.py::test_unsubmitted_form_is_not_reported_as_saved`, `tests/unit/test_ui_autosave.py::test_failed_and_corrupt_storage_preserve_valid_snapshot`.
- **FLOW-004**: приёмка проверена тестами `tests/ui/test_first_month_journey.py::test_first_month_without_all_cell_pins_and_technical_operations`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

FLOW-002/003: origin-local browser storage с Web Locks; quota/error/conflict не перезаписывают snapshot. Неприменённые формы имеют отдельный статус; серверного хранения нет. Streamlit minimum1.65.0 согласован с используемыми widgets. Первый месяц рассчитан независимо, без полного закрепления ячеек.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

## 2026-10-11 — dev delivery и закрытие контракта

Реализация: `922b0c09dfc96698e62e1db414b794f07ba11576` (`feat: deliver reliable authoring, stable repair and two-month quality`). `git push origin dev` прошёл; локальный HEAD и origin/dev совпали, рабочее дерево чистое. До коммита `check_sdd.py --staged` и hooks прошли; перед push `check_sdd.py --base HEAD~1` и project_context --check прошли. Все критерии/задачи текущего контракта проверены; status complete означает реализацию и dev delivery.

[PR66 dev→test](https://github.com/666bes666/duty-schedule-gen/pull/66) обновляется автоматически новым dev head. CI на новом SHA запущен; test/main promotion не выполнен и требует зелёного CI и одного required approving review. Это ограничение доставки релиза, а не непроверенное поведение закрытого контракта.

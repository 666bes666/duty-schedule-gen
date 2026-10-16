# Evidence 016

## 2026-10-11 — согласованный режим

REPAIR-001/002 основаны на прямом выборе владельца: менять как можно меньше
остальных назначений при повторном расчёте. PLOG-08 воспроизвёл 1 → 4 revisions
после трёх no-op checks. Текущий runtime не обеспечивает baseline objective;
новые tests и реализация не выполнялись. Status planned. Gates документов — 013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **REPAIR-001**: приёмка проверена тестами `tests/integration/test_replanning.py::test_both_engines_preserve_valid_baseline_and_pins`, `tests/unit/test_replanning.py::test_hours_and_rename_count_by_identity`, `tests/unit/test_replanning.py::test_nonzero_repair_matches_exhaustive_oracle`, `tests/unit/test_replanning.py::test_nonzero_repair_without_optional_solver_preserves_cells`, `tests/unit/test_replanning.py::test_small_repair_matches_independent_minimum_oracle`.
- **REPAIR-002**: приёмка проверена тестами `tests/ui/test_replanning_journey.py::test_default_repair_and_explicit_rebuild_show_changed_cells`, `tests/unit/test_replanning.py::test_failed_repair_does_not_replace_current_version`, `tests/unit/test_replanning.py::test_noop_check_preserves_revision_id`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

REPAIR-001/002: exhaustive oracle проверяет минимум2изменения, CP-SAT proof зависит именно от OPTIMAL change layer; greedy/timeout обозначены bounded, а ready неизменённый baseline — proven_zero. Failed candidate сохраняется отдельно; no-op check не создаёт новую ревизию.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

## 2026-10-11 — dev delivery и закрытие контракта

Реализация: `922b0c09dfc96698e62e1db414b794f07ba11576` (`feat: deliver reliable authoring, stable repair and two-month quality`). `git push origin dev` прошёл; локальный HEAD и origin/dev совпали, рабочее дерево чистое. До коммита `check_sdd.py --staged` и hooks прошли; перед push `check_sdd.py --base HEAD~1` и project_context --check прошли. Все критерии/задачи текущего контракта проверены; status complete означает реализацию и dev delivery.

[PR66 dev→test](https://github.com/666bes666/duty-schedule-gen/pull/66) обновляется автоматически новым dev head. CI на новом SHA запущен; test/main promotion не выполнен и требует зелёного CI и одного required approving review. Это ограничение доставки релиза, а не непроверенное поведение закрытого контракта.

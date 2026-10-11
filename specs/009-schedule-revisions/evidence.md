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

## 2026-10-11 — уточнение контракта после продуктового интервью 013

Основные правки выполняются в приложении; текущая версия проекта — источник анализа/выдачи, Excel/PDF не являются альтернативной редактируемой истиной. REV-001 дополнен идемпотентностью одинаковой проверки: при неизменённом ready входе/результате новая ревизия назначений не создаётся. REV-002 сохраняет весь backup/recovery payload; browser adapter определён FLOW-002/003. Старый результат реализации не доказывает эти новые критерии.

Новые критерии НЕ реализованы. Прежние PASS выше сохраняются как история
проверки прежних требований; они не доказывают устранение PLOG или выполнение
новых сценариев. Новые test selectors запланированы, исходники/тесты не изменены.
Status возвращён в planned. Анализ и gates документов: evidence013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **REV-001**: приёмка проверена тестами `tests/unit/test_project.py`, `tests/unit/test_ui_workflow.py::test_revision_comparison_displays_changed_individual_workday_hours`, `tests/ui/test_project_journey.py`, `tests/unit/test_replanning.py::test_noop_check_preserves_revision_id`.
- **REV-002**: приёмка проверена тестами `tests/unit/test_project.py::test_project_round_trip_preserves_revisions_and_hours`, `tests/unit/test_project.py::test_invalid_saved_changelog_is_rejected_before_replacing_project`, `tests/unit/test_project.py::test_load_reconstructs_entire_active_month_dependency_chain`, `tests/ui/test_project_journey.py`, `tests/ui/test_product_recovery.py::test_browser_reload_restores_current_project_and_hours`.
- **REV-003**: приёмка проверена тестами `tests/unit/test_project.py::test_edit_pins_both_changed_participants`, `tests/unit/test_ui_workflow.py::test_ui_range_preserves_configuration_and_manual_pins_of_each_period`, `tests/ui/test_project_journey.py`.
- **REV-004**: приёмка проверена тестами `tests/contract/test_revision_api.py::test_forged_ready_schedule_cannot_be_exported`, `tests/unit/test_cli_project.py`, `tests/ui/test_project_journey.py`.
- **REV-005**: приёмка проверена тестами `tests/unit/test_replanning.py::test_small_repair_matches_independent_minimum_oracle`, `tests/integration/test_replanning.py::test_both_engines_preserve_valid_baseline_and_pins`, `tests/unit/test_replanning.py::test_failed_repair_does_not_replace_current_version`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

## 2026-10-11 — dev delivery и закрытие контракта

Реализация: `922b0c09dfc96698e62e1db414b794f07ba11576` (`feat: deliver reliable authoring, stable repair and two-month quality`). `git push origin dev` прошёл; локальный HEAD и origin/dev совпали, рабочее дерево чистое. До коммита `check_sdd.py --staged` и hooks прошли; перед push `check_sdd.py --base HEAD~1` и project_context --check прошли. Все критерии/задачи текущего контракта проверены; status complete означает реализацию и dev delivery.

[PR66 dev→test](https://github.com/666bes666/duty-schedule-gen/pull/66) обновляется автоматически новым dev head. CI на новом SHA запущен; test/main promotion не выполнен и требует зелёного CI и одного required approving review. Это ограничение доставки релиза, а не непроверенное поведение закрытого контракта.

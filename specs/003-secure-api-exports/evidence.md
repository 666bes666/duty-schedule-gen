# Evidence: Безопасный API и экспорт

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

Типизированные plan/revision endpoints добавлены без удаления экспорта из Config. Native422 используется для входной модели и диапазона, прежний unknown employee400 сохраняется; diagnostic даёт409 в legacy generate/export. PDF экранирует имена в обеих таблицах и использует URLFetcher без разрешённых протоколов. Персональные ICS используют VALUE=TEXT; скачивания и ZIP имеют безопасные уникальные leaf names.

Продуктовый контракт сохранён в decisions.md изменения004. Перед реализацией были spec/plan/tasks/traceability. Реальные регрессии выявили и закрыли shared approvals order, active-month dependency gaps, malformed changelog, per-period pins loss, What-if CalendarError, unavailable fairness pool и packaged smoke context.

Независимое ревью: domain_python_review (Python/domain), integration_code_review (UI/project integration), api_security_delivery_review (API/security/delivery). Исполнители не коммитили; root независимо просмотрел fixes, ревьюеры повторно проверили root fixes. Новых CRITICAL/HIGH в проверенной области не осталось. Исторический исход планирования выше сохранён.

Общие команды, runtime результаты и ограничения: [evidence поставки](../011-delivery-assurance/evidence.md). Окончательные gates будут добавлены после завершения последнего прогона; текущий статус in-progress.

## 2026-10-11T00:37:32+03:00 — завершение локальной реализации

Критерии проверены связанными тестами: общий прогон750passed, coverage85.73%, браузер7passed, независимые review fixes закрыты. Реальные команды и границы доказательств находятся в [общем evidence](../011-delivery-assurance/evidence.md). Задачи T001–T005 закрыты; статус complete относится к реализации этих требований, не к публикации релиза.

Уточнена граница SEC-002 без изменения runtime: native422 относится к ошибкам
входной модели/диапазона. Существующие бизнес-ошибки duplicate pin/name и unknown
employee сохраняют400; это отдельно проверяет test_api_strict_validation.py.

## 2026-10-11 — миграция к строгому SDD и явная приёмка

Область `files` восстановлена из плана и реальных файлов. Это актуализация
живого контракта, а не утверждение о ретроспективном прохождении нового gate.

| ID | Проверяющие тесты | Evidence |
|---|---|---|
| SEC-001 | `tests/unit/test_export_security.py::test_pdf_names_are_escaped_in_both_tables`, `tests/unit/test_export_security.py::test_pdf_fetcher_blocks_resources_before_opening` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SEC-002 | `tests/contract/test_revision_api.py::test_bad_range_is_native_422_before_generation`, `tests/contract/test_revision_api.py::test_unknown_employee_quotes_and_newline_produce_json`, `tests/contract/test_api_strict_validation.py`, `tests/unit/test_api_errors.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SEC-003 | `tests/contract/test_revision_api.py::test_binary_export_media_types_are_documented`, `tests/contract/test_revision_api.py::test_forged_ready_schedule_cannot_be_exported`, `tests/contract/test_revision_api.py::test_control_characters_in_employee_name_export_as_escaped_calendar_text`, `tests/unit/test_export_security.py::test_archive_names_are_safe_unique_and_preserve_original_inputs` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

## 2026-10-11 — уточнение контракта после продуктового интервью 013

Для SEC-002 несовместимый период полного календаря и неизвестный путь what-if являются ошибкой входа native 422 до поиска/сети. Реальный сбой источника календаря сохраняет 502; прежние бизнес-ошибки 400 и export 409 сохраняются. См. DATA-003/004 изменения 014.

Новые критерии НЕ реализованы. Прежние PASS выше сохраняются как история
проверки прежних требований; они не доказывают устранение PLOG или выполнение
новых сценариев. Новые test selectors запланированы, исходники/тесты не изменены.
Status возвращён в planned. Анализ и gates документов: evidence013.

## 2026-10-11 — проверка реализации 014–017

Новая реализация проверена на текущем diff от `97a591bfe1b8728ce74d7618027605c800008736`; исторические результаты выше сохранены.

- **SEC-001**: приёмка проверена тестами `tests/unit/test_export_security.py::test_pdf_names_are_escaped_in_both_tables`, `tests/unit/test_export_security.py::test_pdf_fetcher_blocks_resources_before_opening`.
- **SEC-002**: приёмка проверена тестами `tests/contract/test_revision_api.py::test_bad_range_is_native_422_before_generation`, `tests/contract/test_revision_api.py::test_unknown_employee_quotes_and_newline_produce_json`, `tests/contract/test_api_strict_validation.py`, `tests/unit/test_api_errors.py`, `tests/contract/test_product_inputs.py::test_mismatched_calendar_is_422_without_search_or_network`, `tests/contract/test_product_inputs.py::test_unknown_nested_patch_is_422_without_search`.
- **SEC-003**: приёмка проверена тестами `tests/contract/test_revision_api.py::test_binary_export_media_types_are_documented`, `tests/contract/test_revision_api.py::test_forged_ready_schedule_cannot_be_exported`, `tests/contract/test_revision_api.py::test_control_characters_in_employee_name_export_as_escaped_calendar_text`, `tests/unit/test_export_security.py::test_archive_names_are_safe_unique_and_preserve_original_inputs`.

Полный проверенный прогон до последних review fixes: 839 passed, coverage 87.52%; browser18 passed. После последних fixes целевой прогон34 passed; независимые ревьюеры semantic_review_g (47 passed, Python) и semantic_review_h (42 passed, integration) дали PASS на исправленном diff. Ruff lint/format и mypy69файлов прошли. Итоговые стабильные полные прогоны, wheel smoke и dev SHA добавляются ниже после завершения.

## 2026-10-11 — итоговые локальные gates

849 non-UI tests passed, coverage88.18%;18browser tests passed;16additional targeted passed после двух acceptance tests. Runtime стабильный. Ruff/mypy/SDD/index/wheel/audit и независимое dual PASS: [общие реальные команды и ограничения](../014-product-reliability/evidence.md). Dev delivery добавляется после push.

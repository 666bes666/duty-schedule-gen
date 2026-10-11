# Задачи: Безопасный API и экспорт

## US1 — Проверяемое поведение

- [x] T001 [US1] Регрессии SEC-001..003 в tests/unit/test_export_security.py, tests/unit/test_api_errors.py, tests/contract/test_revision_api.py.
- [x] T002 [US1] Реализация требований в src/duty_schedule/api/, src/duty_schedule/export/pdf.py, tests/contract/.
- [x] T003 [US1] Интеграция общих моделей и совместимость по specs/003-secure-api-exports/plan.md.
- [x] T004 [US1] Проверка критериев и независимое ревью затронутых файлов.
- [x] T005 Evidence, traceability и фактически выполненные общие gates в specs/003-secure-api-exports/evidence.md.

## Порядок

T001 -> T002 -> T003 -> T004 -> T005. Независимые тесты можно выполнять параллельно;
мутации одного файла координируются одним владельцем. Нет непроверенных завершённых
задач. Модель/контракт предшествуют адаптерам, финальная проверка — экспорту.


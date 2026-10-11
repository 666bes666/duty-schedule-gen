# Задачи: Версии графика и файл проекта

## US1 — Проверяемое поведение

- [x] T001 [US1] Регрессии REV-001..004 в tests/unit/test_project.py, tests/contract/test_revision_api.py.
- [x] T002 [US1] Реализация требований в src/duty_schedule/project.py, src/duty_schedule/models.py, src/duty_schedule/ui/, app.py.
- [x] T003 [US1] Интеграция общих моделей и совместимость по specs/009-schedule-revisions/plan.md.
- [x] T004 [US1] Проверка критериев и независимое ревью затронутых файлов.
- [x] T005 Evidence, traceability и фактически выполненные общие gates в specs/009-schedule-revisions/evidence.md.

## Порядок

T001 -> T002 -> T003 -> T004 -> T005. Независимые тесты можно выполнять параллельно;
мутации одного файла координируются одним владельцем. Нет непроверенных завершённых
задач. Модель/контракт предшествуют адаптерам, финальная проверка — экспорту.


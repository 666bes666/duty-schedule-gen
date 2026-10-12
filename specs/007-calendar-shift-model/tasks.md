# Задачи: Календарь и временная модель

## US1 — Проверяемое поведение

- [x] T001 [US1] Регрессии TIME-001..003 в tests/unit/test_calendar_model.py, tests/unit/test_ics_per_employee.py.
- [x] T002 [US1] Реализация требований в src/duty_schedule/calendar.py, src/duty_schedule/models.py, src/duty_schedule/export/ics.py, src/duty_schedule/stats.py, src/duty_schedule/costs.py.
- [x] T003 [US1] Интеграция общих моделей и совместимость по specs/007-calendar-shift-model/plan.md.
- [x] T004 [US1] Проверка критериев и независимое ревью затронутых файлов.
- [x] T005 Evidence, traceability и фактически выполненные общие gates в specs/007-calendar-shift-model/evidence.md.

## Порядок

T001 -> T002 -> T003 -> T004 -> T005. Независимые тесты можно выполнять параллельно;
мутации одного файла координируются одним владельцем. Нет непроверенных завершённых
задач. Модель/контракт предшествуют адаптерам, финальная проверка — экспорту.


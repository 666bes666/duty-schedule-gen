# План минимального пересчёта

Python 3.12+, uv; project/scheduler/rules/validator границы сохраняются.
Dev, явный feature directory и NO_PERSIST=1. После 014 и приоритетного 015.

Project orchestration передаёт detached baseline в search; solver добавляет
целевой слой changed employee-day pairs перед качеством, greedy начинает с
допустимых сохранённых ячеек и bounded repair. В обоих режимах финальный validator
проверяет hard rules/norm/pins. Baseline нельзя навсегда закрепить новым набором
пинов, иначе новое ограничение стало бы неисправимым.

Idempotent check сохраняет revision ID при равном входе и выводе; checking event
не маскируется изменением назначений. При applied repair создаётся revision с
причиной и списком изменённых ID/day/hours, зависимые месяцы проверяются заново.
Failed candidate остаётся отдельным диагностическим результатом для просмотра.

Scope и planned selectors: traceability.json. Unit/project integration,
малый exhaustive oracle, обе search стратегии, actual UI preserved baseline,
SDD/index/Ruff/mypy/full pytest/UI/coverage >=80%. Общий HTTP интерфейс без
baseline не меняется; новый API repair потребует отдельного scoped контрактного решения.

## Анализ перед реализацией 2026-10-11
REPAIR-001→T001/T002/T004; REPAIR-002→T003/T005/T006. Контракт согласован.
Общая метрика использует employee_id/date, shift и фактические assignment_hours.
Ready baseline при новом входе возвращается с zero edits и доказанным минимумом 0.
При нарушениях CP-SAT добавляет Boolean OR(state changed, hours changed) перед
quality layers; greedy использует bounded CP repair при доступной optional solver,
иначе обычный bounded кандидат с честным heuristic marker. Сохранённые клетки
не становятся pins. Failed candidate хранится отдельно в ScheduleProject и
применяется только явной UI кнопкой; current revision не заменяется автоматически.
check_current обновляет запись проверки при одинаковом input key без новой revision.

Диапазон UI вызывает тот же baseline-aware project orchestration для каждого периода; failed candidate прерывает диапазон. CP proof связывается с OPTIMAL именно change layer, а календарное изменение фактических часов учитывается как changed cell.

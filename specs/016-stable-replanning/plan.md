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

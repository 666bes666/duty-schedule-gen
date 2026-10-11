# План аудита

## Контекст и конституция

Python3.12+, uv, stdlib для tooling; действующие FastAPI/Streamlit/Pydantic/OR-Tools.
Работа напрямую в dev. SPECIFY_FEATURE_DIRECTORY=$PWD/specs/012-project-audit,
SPECIFY_FEATURE_NO_PERSIST=1; чужие изменения сохраняются. Исходное дерево чистое.

## Решения и границы

1. Сначала воспроизвести обходы текущего SDD gate отдельными тестами.
2. `scripts/check_sdd.py`: bidirectional IDs, exact file scope, task IDs, реальные
   собираемые test nodes; --base включает рабочие файлы, --staged использует
   temporary checkout-index snapshot. Ошибки Git/encoding/symlinks — fail closed.
   Допустимы planned тесты, ещё не существующие; complete проверяет их содержание.
3. Обновить traceability всех изменений явными файлами из существующих планов и
   приёмкой в evidence. Исходные результаты сохранять; новый аудит добавлять датой.
4. Уточнить SDD-003/004/006 изменения001, планы/задачи и evidence; новая012
   спецификация содержит проверяемое расширение. Обновить конституцию1.1.0,
   руководства, шаблоны и hook/workflows. SDD охватывает любой тип изменения.
5. `scripts/project_context.py`: deterministic JSON/Markdown index из git ls-files
   и AST; --write/--check/context. Generated files включают собственные пути без
   self hashes/timestamps. Live Git/feature context вычисляется при запуске.
6. Проверить cold start в disposable clone, включая изолированное locked окружение.
7. Удалить retired `_build_day`/три селектора из greedy.py и re-export; заменить
   unit сценарии ограничений на текущий build_candidate. Удалить stub
   `_shift_limit_reached` из constraints.py после проверки отсутствия вызовов. Убрать лишний параметр
   employees_df из dashboard и kwargs warning, сохранив callback интерфейс.
   NOTES — архив устаревших комментариев, удалить; ARCHITECTURE переписать по
   actual source и живым контрактам. Зафиксировать retained adapters в audit.md.
8. Сверить GitHub branch protections с реальными check runs. Добавить SDD на
   dev/test/main и actual renamed main checks; preserve approvals, запреты force
   push/deletion и остальные настройки. Merge через GitHub после CI; blockers
   фиксировать честно, без обхода review policy.

## Проверки

tests/unit/test_sdd.py: invalid structures, omitted IDs, duplicate tasks, false
test selectors, missing evidence IDs, scoped committed/worktree/staged diff,
deleted/renamed files и подмена unstaged документами.
tests/unit/test_project_context.py: deterministic complete inventory, ignored files,
drift, symbols/imports/API/spec paths, live context и broken sources.
tests/unit/test_constraints.py: актуальный генератор вместо retired helper.
tests/unit/test_delivery_workflows.py: CI/hook/index gates, existing release chain.

Ruff src/tests/scripts/app.py/api_main.py; mypy src/scripts; full non-UI pytest
с coverage; UI/Playwright; Bandit/pip-audit; uv build/installed smoke; cold clone;
SDD --base f5ae141 и --staged; GitHub CI dev/test/main с platform/packaged gates.

## Риски

Exact scope требует обновления при новом файле; это намеренное ограничение.
AST не доказывает смысл assertion; semantic review обязателен. Состояние GitHub
внешнее и может изменяться; evidence имеет дату и links. Independent review
может зависеть от доступного reviewer; пропуск не становится одобрением.

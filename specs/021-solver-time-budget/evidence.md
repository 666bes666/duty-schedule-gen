# Evidence

## 2026-10-19 — реализация и проверка

Исходный commit: dab9bff34934f821582c989c7ce558c3e39d513e, ветка dev. Среда: macOS,
Python 3.12.12, `uv sync --locked --dev --extra solver`, для PDF
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

Воспроизведение. Стресс-скрипт вне репозитория строил 400 случайных конфигураций
(2025–2026, 4–9 Москва, 2–4 Хабаровск, 5/2, только утро/вечер, вне дежурств,
отпуска до 14 дней, больничные, недоступные даты, еженедельные выходные, персональные
серии). Из них 32 отвергнуты валидацией Config. До изменения: 107 ready,
261 diagnostic, ни одного падения, ни одного ready, который не прошёл бы повторную
`validate_schedule_result`. На 36 неуспешных greedy-случаях прямой CP-SAT дал ready
в трёх. Замер `solve_schedule(timeout=3)` для двух из них: `timeout` через 0,53 с;
при `timeout=10` ready за 2,2–3,1 с.

После изменения те же два месяца при `timeout=3` получают ready за 1,6 и 2,5 с.
Доказанно невыполнимые месяцы возвращаются за то же время (0,04 и 0,38 с). Тот же
стресс-прогон: 124 ready (+17), 244 diagnostic, падений и ложных ready нет, ни один
расчёт не превысил 20 с.

Приёмка требований:

- BUDGET-001: `test_first_layer_timeout_retries_with_remaining_budget` — второй
  вызов получает лимит `6 − доля`, результат ready.
  `test_budget_exhausted_by_first_layer_keeps_timeout_status` — сумма лимитов 6 с,
  статус `timeout`, диагностический черновик. PASS.
- BUDGET-002: `test_found_first_solution_keeps_layer_slices` — все лимиты равны
  доле. `test_later_layer_timeout_does_not_retry` — UNKNOWN второго слоя не
  повторяется, ready сохраняется. Существующие solver/planning/system тесты PASS.
- BUDGET-003: флаг `first_solution_retry` true/false в тех же тестах. PASS.

RED: на исходном `solver.py` все четыре новых теста падают (два по поведению
повтора, два по отсутствию флага). GREEN после изменения.

Команды:

- `uv run ruff check src/ tests/ scripts/ app.py api_main.py`: PASS.
- `uv run ruff format --check src/ tests/ scripts/ app.py api_main.py`: PASS.
- `uv run mypy src/ scripts/`: PASS, 71 source files.
- `uv run python scripts/check_sdd.py --base HEAD`: PASS.
- `uv run python scripts/project_context.py --check`: PASS.
- `uv run pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-fail-under=80`:
  886 passed, 4 skipped, coverage 88 %.

Ограничения: UI/Playwright не запускались, UI не затронут. Число ready в стресс-
прогоне зависит от скорости машины, потому что лимиты CP-SAT заданы по wall time;
unit тесты от тайминга не зависят. Отдельное ревью другим человеком не проводилось.

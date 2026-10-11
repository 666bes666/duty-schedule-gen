# План двухмесячного качества

Python 3.12+, uv; общая domain quality model/calculator, project sources,
оба search алгоритма, stats/API/UI consumers. Dev, feature directory и NO_PERSIST=1.
После 014/015/016, без нового влияния на hard validity.

Typed quality context хранит период/source revision, employee_id, выбранные часы,
подходящие виды дежурств и проверенные counts предыдущего месяца. Project получает
его из active previous revision после общей проверки. Внешний optional input —
полный snapshot предыдущего Schedule: общий validator проверяет его правила,
часы, календарь и историю, а calculator заново получает counts/нормы/пулы.
Происхождение external и отсутствие доказательства active project revision
обозначаются явно; одни присланные неотрицательные агрегаты не дают verified history.
Отсутствие context отличают от проверенного нулевого вклада нового сотрудника.

Общий calculator формирует cumulative counts/selected-hour weights по каждому
подходящему виду и периоду. Solver objective и greedy/postprocess/summary используют
одни компоненты/пулы; историческая unavailable роль не увеличивает entitlement.
Персональное предпочтение — последний tie-break, deprecated priority — warning.
Stats разделяет month-only и boundary metrics; provenance появляется в display.

Exact scope и planned selectors: traceability.json. API добавления рассматриваются
как optional backward-compatible; runtime contract tests и OpenAPI snapshot обязательны
при изменении schema. Необходимые новые source paths объявляются до реализации.

Проверки: two_month_quality unit/integration, role/norm/history/source fixtures,
обе стратегии поиска, unknown history, Summary/UI/export согласованность;
SDD/index/Ruff/mypy/full pytest/UI/coverage >=80%. Legacy standalone clients
не обязаны предоставлять fictitious previous history для существующего ready пути.

## Анализ перед реализацией 2026-10-11
QUALITY-001→T001/T003; QUALITY-002→T002/T005; QUALITY-003→T004/T006/T007.
Общий optional Config.previous_schedule — полный предыдущий snapshot, не агрегаты.
Calculator заново валидирует его и проверяет соседний календарный период; неверный
snapshot даёт month-only/unavailable marker. Project использует только active
previous с актуальными dependencies. Вход external не подтверждает active revision.
Пулы индексируются employee_id; сохраняются выбывшие сотрудники и бывшие подходящие
роли, веса начисляются только eligible периодам. Fraction сохраняет точное сравнение;
CP objectives используют общий integer scale через lcm знаменателей, без округления.
Preferences — пятый мягкий слой у calculator/solver; greedy улучшает bounded кандидаты
общим comparator. Boundary streak отдельный от month-only; summary и выдача содержат
window/source/pools/quality components. Legacy priority даёт явное предупреждение.

Объявлен pipeline.py: его type signature принимает точные Fraction компоненты общего quality_key без изменения алгоритма.

Точный response schema contract обновляется для additive полей boundary_max_streak_work/rest и quality_context; старые поля сохранены. Путь объявлен перед изменением.

Ранее unit quality[-1] означал off-balance, теперь preference layer последний: test_planning_rules.py использует index3. test_whatif_service.py согласует реальные assignments со своим independent ожидаемым балансом; summary больше не доверяет противоречивым stats counters. Эти test paths объявлены до изменения.

## 2026-10-11 — завершение дополнительного независимого ревью

QUALITY-002: центральный append revision проверяет external snapshot против active ID/config/days и ready; form serialization не восстанавливает stale источник. QUALITY-003: PDF HTML собирается после boundary table; внешний source ID XLS санитизируется. Добавлены runtime/API/renderer регрессии в уже согласованной области files.

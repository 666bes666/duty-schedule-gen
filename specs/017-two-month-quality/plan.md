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

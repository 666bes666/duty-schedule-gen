# Анализ до реализации

Проверены constitution, docs/sdd, `scheduler/solver.py`, `scheduler/core.py`
(greedy repair с `timeout=3`), `tests/unit/test_solver.py` и VALID-004. Metadata
решателя свободного формата: `objective_values`, `repair_optimality` и
`duration_ms` не входят в OpenAPI snapshot и публичную схему проекта, новый ключ
совместим. Статусы `timeout`/`infeasible`/`feasible`/`optimal` сохраняются.
Каждый BUDGET ID связан с тестом; scope точный. Открытых продуктовых решений нет.

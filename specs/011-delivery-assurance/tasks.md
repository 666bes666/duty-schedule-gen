# Задачи: Проверки и проверяемая поставка

## US1 — Проверяемое поведение

- [x] T001 [US1] Регрессии DEL-001..004 в tests/unit/test_delivery_workflows.py.
- [x] T002 [US1] Реализация требований в .github/workflows/, .github/actions/setup-python/action.yml, Dockerfile, tests/ui/, tests/e2e/, scripts/.
- [x] T003 [US1] Интеграция общих моделей и совместимость по specs/011-delivery-assurance/plan.md.
- [x] T004 [US1] Проверка критериев и независимое ревью затронутых файлов.
- [x] T005 Evidence, traceability и фактически выполненные общие gates в specs/011-delivery-assurance/evidence.md.

## Порядок

T001 -> T002 -> T003 -> T004 -> T005. Независимые тесты можно выполнять параллельно;
мутации одного файла координируются одним владельцем. Нет непроверенных завершённых
задач. Модель/контракт предшествуют адаптерам, финальная проверка — экспорту.



## macOS gate — 2026-10-13

- [x] T006 Зафиксировать failure и planned критерии/traceability до CI изменений.
- [x] T007 Regression wiring test и native runtime preparation/smoke перед pytest.
- [x] T008 Native smoke/AppTest, общие gates и независимое review.
- [x] T009 Обновить evidence/index и закрыть после зелёного macOS CI обоихPython.

## Сопоставимость benchmark — 2026-10-16

- [x] T010 Проверить повторный failure и уточнить DEL-003, plan/traceability/analysis до кода.
- [x] T011 Regression tests: prior SHA, fresh report, isolated runtime, cleanup, fail closed, оба workflow.
- [x] T012 Opt-in remeasurement helper и full-history wiring обоих performance jobs.
- [x] T013 Реальный replay + compare, общие локальные gates, независимое ревью и evidence.

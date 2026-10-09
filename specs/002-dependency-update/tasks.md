# Задачи обновления зависимостей

## Основа

- [x] T001 Воспроизвести исходный аудит и подготовить specs/002-dependency-update/spec.md, plan.md, traceability.json.

## US1 — Безопасное воспроизводимое окружение

- [x] T002 [US1] Обновить security-минимумы pyproject.toml, все группы uv.lock и Ruff rev в .pre-commit-config.yaml.
- [x] T003 [US1] Синхронизировать базовое/расширенное окружения и записать результаты pip-audit в specs/002-dependency-update/evidence.md.

## US2 — Совместимость продукта

- [x] T004 [US2] Проверить tests/contract, tests/unit, tests/integration, tests/system, tests/e2e, solver и сборку; выполнить минимальные адаптации при выявленных регрессах.
- [x] T005 [P] [US2] Провести независимое ревью изменения pyproject.toml/uv.lock/кода и согласованности спецификации.
- [ ] T006 [US2] Записать evidence в specs/002-dependency-update/evidence.md; commit/push в dev, обновить PR #66 и проверить CI.

Зависимости: T001 → T002 → T003/T004; T005 после готового diff; T006 после локальной
приёмки и ревью. Аудит и тесты используют одно окружение и выполняются последовательно
после sync. Отдельное native/browser окружение допускается параллельно ревью.

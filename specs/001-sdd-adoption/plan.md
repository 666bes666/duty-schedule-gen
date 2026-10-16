# План перехода на SDD

## Решения

1. Инициализировать Spec Kit 1.1.3 в отдельной временной директории, перенести
   только `.specify/`, `.agents/skills/`, `.claude/skills/`. Сохранить официальные
   скрипты без расширения `git`, настроить конституцию и добавить локальные
   правила в шаблоны. Локальный указатель `.specify/feature.json` не коммитить.
2. Зафиксировать ограниченный baseline исходного HEAD
   `949b6bc53ba649d496d130545acb81a8dc6f656d`: требования, test mapping,
   известные расхождения и снимок OpenAPI. Не исправлять продукт в этой миграции.
3. Добавить `scripts/check_sdd.py` на стандартной библиотеке Python. Все
   `specs/*/traceability.json` проверяются независимо от активной спецификации
   агента. Различать baseline, draft, specified, planned, in-progress, complete.
4. При `--base` получить diff от BASE до worktree вместе с untracked;
   требовать exact scope обновлённого planned-контракта для каждого файла.
   Недоступный base — ошибка. Pre-commit `--staged` проверяет temporary snapshot
   Git index; без base проверяется структура. Уточнение поведения: аудит012.
5. Запустить проверку в отдельном CI workflow на push/PR `dev`, `test`, `main`
   и в pre-commit. Контрактный snapshot-тест включить в SDD gate, поскольку
   основной dev workflow пока не запускает `tests/contract`.
6. Согласовать инструкции и PR template. Новых runtime-зависимостей нет.

## Соответствие конституции

- Прямые изменения в `dev`; feature-ветки не создаются.
- Публичное поведение приложения сохраняется.
- Управление окружением — `uv`; новые скрипты типизированы и проверяются Ruff.
- Новые проверки покрыты позитивными и негативными тестами.
- Результаты, пропуски и независимое ревью записываются в evidence.

## Проверки

```bash
uv run python scripts/check_sdd.py
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run mypy src/
uv run pytest tests/ -q --ignore=tests/ui
```

Отдельно: helpers Spec Kit в disposable git-репозитории на `dev`; негативные
сценарии валидатора; проверка diff gate с base-коммитом; drift OpenAPI;
независимое ревью всех изменений. Автоматическое продвижение в `test`/`main`
и публикация релиза в задачи миграции не входят.

## 2026-10-11 — расширение по аудиту012

Прежний runtime-only linkage расширен на все типы изменений и точные `files`.
`--base` включает worktree/untracked; pre-commit `--staged` валидирует snapshot
Git index. SDD-003/004/006 проверяются новыми негативными тестами test_sdd и
test_project_context; полный индекс проверяется SDD CI. Старый процесс соблюдён,
дополнительный анализ/реализация/evidence находятся в012.

## Аудит012 — scope интеграции и продвижения

Сверка фактического cumulative diff к test/main дополнительно подтвердила
принадлежность следующих файлов этому контракту:

- `scripts/export_openapi.py`

Это уточнение области уже реализованных требований, не изменение смысла ID.
Результаты исходной реализации сохраняются; новый scoped gate и полный повторный
прогон отражены в evidence012.

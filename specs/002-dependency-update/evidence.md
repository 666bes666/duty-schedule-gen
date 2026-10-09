# Результаты обновления зависимостей

Дата: 2026-10-10, Europe/Moscow. Исходный HEAD:
`423774f2bc81152b7ff509b5334aa6d11935d68b`.

## Изменения

Обновлены 74 пакета, удалены 8 больше не требуемых транзитивных зависимостей,
добавлены 2 зависимости обновлённых библиотек. Полная таблица: [versions.json](versions.json).
В universal lock 130 записей; источники — PyPI/files.pythonhosted.org и локальный
editable пакет. Hashes, прежние Python/platform markers сохранены, prerelease нет.

Ключевые версии:

| Пакет | До | После |
|---|---|---|
| anyio | 4.13.0 | 4.15.1 |
| icalendar | 7.1.2 | 7.3.0 |
| msgpack | 1.2.0 | 1.2.3 |
| pillow | 12.2.0 | 12.3.0 |
| pip | 26.1.2 | 26.2.1 |
| pydantic-settings | 2.14.1 | 2.15.0 |
| urllib3 | 2.7.0 | 2.8.0 |
| virtualenv | 21.5.0 | 21.14.6 |
| weasyprint | 69.0 | 70.0 |
| gitpython | 3.1.50 | удалён: новый Streamlit не требует |
| fastapi | 0.136.3 | 0.143.0 |
| streamlit | 1.58.0 | 1.65.0 |
| ruff | 0.15.17 | 0.17.0 |
| mypy | 2.1.0 | 2.4.0 |

Минимумы metadata подняты для icalendar ≥7.1.3, pydantic-settings ≥2.14.2,
WeasyPrint ≥70. `tool.uv.prerelease="disallow"` сохраняет одинаковые параметры
для lock и обычного sync. Ruff pre-commit закреплён на v0.17.0.

## Приёмка

| ID | Доказательство | Результат |
|---|---|---|
| DEP-001 | uv lock --check; fresh uv sync --locked --all-groups --all-extras | проходит, 127 установленных пакетов |
| DEP-002 | исходный/base/expanded pip-audit; Bandit | было 78 находок в 10 пакетах; оба новых окружения: 0 находок; Bandit проходит |
| DEP-003 | полный pytest, API snapshot, solver/PDF, AppTest, браузер | 619 основных +5 UI тестов прошли; API snapshot не менялся; native PDF и solver не skipped |
| DEP-004 | Ruff, mypy, coverage, build/wheel smoke | проходят; coverage 89,44%; dev/PR CI прошли после push |
| DEP-005 | metadata floors, официальный Ruff manifest, dependency review | security floors и Ruff parity подтверждены |

Команды выполнены через uv. Для расширенного окружения использовались
`--all-groups --all-extras` при sync, затем `--no-sync` при запуске проверок:

```bash
uv lock --upgrade --prerelease disallow
uv lock --check
uv sync --locked --all-groups --all-extras
uv run --no-sync pip-audit --format json --output /tmp/duty-deps-after-all.json
uv run --no-sync bandit -r src/ -c pyproject.toml -q
uv run --no-sync ruff check src/ tests/ scripts/
uv run --no-sync ruff format --check src/ tests/ scripts/
uv run --no-sync mypy src/ scripts/
uv run --no-sync python scripts/check_sdd.py
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run --no-sync pytest tests/ --ignore=tests/ui -o addopts='' -q -ra --benchmark-disable --cov=duty_schedule --cov-report=term --cov-fail-under=80
uv build
uv run --no-project --with dist/duty_schedule-4.0.0-py3-none-any.whl duty-schedule --help
UV_PROJECT_ENVIRONMENT=/tmp/duty-deps-validation.F58RhU UV_NO_SYNC=1 DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run --no-sync pytest tests/ui -o addopts='' -q -ra
```

- Основной pytest: **619 passed, 0 skipped**, 67,35 с; coverage **89,44%**.
  Два сторонних DeprecationWarning об инверсии bool не являются ошибками.
- UI/Chromium: **5 passed**, 19,68 с. Это существующие browser smoke-тесты.
- Ruff: 135 файлов форматированы; mypy: 52 файла без ошибок.
- Базовое окружение собрано заново в отдельном virtualenv через
  `uv sync --locked --dev --group ci-security`: 116 пакетов, аудит 0 находок.
- Расширенное окружение: 127 пакетов, аудит 0 находок.
- В обоих audit-отчётах локальный unpublished `duty-schedule` пропущен PyPI
  сервисом; внешние зависимости проверены, исходники отдельно проверены Bandit.
- Wheel и sdist успешно собраны; CLI --help из wheel работает.

## Дополнительные проверки совместимости

Python reviewer выполнил Streamlit AppTest с mock календаря и кликнул
«Сгенерировать расписание»: exception/error пустые, сформированы 30 дней ноября
2026 для 8 сотрудников, 12 download widgets (8 ICS, XLS, PDF, 2 YAML), проверены
сигнатуры XLS PK/PDF %PDF и число дней. Это проверка выполнения UI и содержимого
downloads, а не физического скачивания через браузер. Вызовы use_container_width
выдают существующие deprecated warnings; функциональность работает.

Репрезентативный PDF из config.example.yaml: март 2025, 11 сотрудников, 31 день,
42095 байт. Native Pango/Cairo уже установлены; использован DYLD fallback path,
системные пакеты не устанавливались. Рендер через pypdfium2 и визуальная проверка:
одна страница A3 landscape (1190,55×841,89 pt), заголовок, таблицы, статистика и
легенда читаемы и не обрезаны. Артефакты временные: /tmp/duty-deps-pdf-validation/.

## Ревью

- code-reviewer: APPROVE, CRITICAL/HIGH/MEDIUM/LOW — 0; проверены sources/hashes,
  universal markers, отсутствие prerelease, floors и официальный Ruff hook manifest.
- python-reviewer: APPROVE; metadata не содержит отсутствующих/конфликтующих
  зависимостей, Python 3.12 поддерживается; cp312/cp313 wheels для native пакетов
  представлены для Linux/macOS/Windows; выполнен AppTest выше.
- security-reviewer: опубликованные non-yanked версии и upstream changelogs
  подтверждены; окончательный security-результат получен свежим pip-audit.

## Локальные ограничения и исправленные проблемы окружения

Первый browser-запуск не импортировал editable пакет: Python 3.12 пропускает .pth,
помеченные macOS UF_HIDDEN в рабочем .venv. Снятие флага восстанавливало import,
но флаг появлялся вновь между вызовами инструментов. Повторная проверка выполнена
в freshly synced virtualenv вне рабочей папки через UV_PROJECT_ENVIRONMENT и прошла.
Это ограничение локального окружения; код/контракт не изменялись ради его обхода.

Benchmark assertions включены в основной pytest, измерительные циклы отключены
--benchmark-disable; штатный performance CI выполняет benchmark отдельно.
PDF проверен на одном репрезентативном составе, визуальная идентичность всех
возможных документов не утверждается. Аудит — состояние доступной базы advisory
на момент запуска, без suppression или отключения gates.

## Доставка

Локальная приёмка завершена. Осталась проверка dev/PR CI после commit/push;
T006 и статус complete закрываются после получения фактических результатов.
Версия приложения не изменяется, main/release не продвигаются.


### GitHub CI после push

Проверен commit `6faea7ae6f507344eb280d0f6cc96bcd66cfe745`:

- [CI Dev](https://github.com/666bes666/duty-schedule-gen/actions/runs/38002941627):
  все jobs success, включая Dependency Audit.
- [SDD Gate dev](https://github.com/666bes666/duty-schedule-gen/actions/runs/38002941644): success.
- [CI Test PR #66](https://github.com/666bes666/duty-schedule-gen/actions/runs/38002945153):
  Security Scan, Lint + Mypy, Streamlit Smoke, Performance Benchmarks и все четыре
  test-matrix jobs Linux/Windows × Python 3.12/3.13 — success.
- [SDD Gate PR](https://github.com/666bes666/duty-schedule-gen/actions/runs/38002945130): success.

Предыдущий security-блокер снят фактическими результатами нового CI. T006 и
все требования приняты; статус complete фиксируется отдельным docs-коммитом.
PR #66 готовится к обычному ревью; автоматическое слияние, main и релиз не выполняются.

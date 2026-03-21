# Руководство по вкладу в проект

## Начало работы

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync --dev
uv run pre-commit install
```

Для работы с CP-SAT solver:

```bash
uv sync --dev --extra solver
```

## Ветвление и workflow

Проект использует трёхуровневый pipeline:

```
dev ──PR──> test ──PR──> main
```

| Ветка | Назначение | CI |
|-------|-----------|-----|
| `dev` | Интеграция фич, быстрая проверка | ci-dev.yml (~20 сек) |
| `test` | Стабилизация, расширенное тестирование | ci-test.yml (~45 сек) |
| `main` | Production, полная регрессия | ci-main.yml (~2 мин) |

### Создание фичи

1. Коммит напрямую в `dev` (без feature-веток)
2. Push в GitHub сразу после коммита
3. PR из `dev` в `test` — проходит полный набор тестов + security + performance
4. PR из `test` в `main` — полная регрессия + UI + system тесты

### Hotfix

Для критических исправлений:

1. Ветка от `main`: `git checkout -b hotfix/critical-fix main`
2. PR напрямую в `main` — проходит полную регрессию ci-main.yml
3. После мержа — cherry-pick в `dev` и `test`

### Политика пуша

- **Всегда пушить в GitHub сразу** после коммита. Не накапливать локальные коммиты.
- **Мержить PR через GitHub** (`gh pr merge`), а не локально. Это гарантирует прохождение CI и соблюдение branch protection.
- После мержа hotfix PR в `main` — cherry-pick в `dev` и `test`, затем push обоих.

## Стиль кода

- Python 3.12+
- Форматтер: `ruff format`
- Линтер: `ruff check` — все правила из `pyproject.toml`
- Типизация: `mypy` (проверяется в ci-test и ci-main)
- Без комментариев в исходном коде — все заметки идут в `NOTES.md`
- Docstrings не обязательны

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Тесты

```bash
# Все тесты (кроме UI)
uv run pytest tests/ -q --ignore=tests/ui

# По уровням
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/contract
uv run pytest tests/system
uv run pytest tests/e2e

# С покрытием
uv run pytest --cov=duty_schedule --cov-report=term-missing --ignore=tests/ui

# Performance (требует группу ci-perf)
uv sync --dev --group ci-perf
uv run pytest tests/performance --benchmark-only

# UI (требует группу ci-ui)
uv sync --dev --group ci-ui
uv run playwright install chromium
uv run pytest tests/ui
```

Минимальное покрытие: **80%**. CI завершится с ошибкой при меньшем значении.

### Структура тестов

```
tests/
  unit/           # Модульные тесты
  integration/    # Интеграционные тесты
  contract/       # Контрактные тесты (сериализация, форматы)
  e2e/            # End-to-end (CLI workflow)
  performance/    # Бенчмарки (pytest-benchmark)
  system/         # Системные (бизнес-правила, детерминированность)
  ui/             # UI тесты (Playwright + Streamlit)
```

### Конвенции логирования

Event names в вызовах `logger.info/warning/error/debug` должны быть на английском в формате `snake_case`. Регрессионный AST-тест в `tests/unit/test_logging_setup.py` автоматически проверяет это правило.

## Версионирование

Проект использует [семантическое версионирование](https://semver.org/lang/ru/):

```
dev:   X.Y.Z-dev
test:  X.Y.Z-rc.N
main:  X.Y.Z (стабильный релиз)
```

Версия хранится в `src/duty_schedule/__init__.py` и `pyproject.toml`.

## Процесс релиза

1. Обновить версию в `src/duty_schedule/__init__.py` и `pyproject.toml`
2. PR через `dev → test → main`
3. При мерже в `main` — `ci-tag.yml` автоматически создаёт tag `vX.Y.Z`
4. Tag запускает `release.yml` → GitHub Release

## Dependency Groups

```bash
uv sync --dev                           # базовые dev-зависимости
uv sync --dev --extra solver            # + CP-SAT solver (ortools)
uv sync --dev --group ci-security       # + bandit, pip-audit
uv sync --dev --group ci-perf           # + pytest-benchmark
uv sync --dev --group ci-ui             # + playwright
```

## Сообщения коммитов

Используйте [Conventional Commits](https://www.conventionalcommits.org/ru/):

```
feat: добавить поддержку часового пояса Владивостока
fix: исправить подсчёт ночных смен при отпуске
docs: обновить примеры конфигурации
test: добавить тест граничного случая с длинным отпуском
refactor: упростить алгоритм отката
ci: обновить ci-test workflow
```

## Структура проекта

```
src/duty_schedule/
  models.py              # Pydantic v2 модели данных
  calendar.py            # Производственный календарь (isdayoff.ru)
  cli.py                 # CLI (Typer): generate, generate-range, validate, version
  logging.py             # Структурированное логирование (structlog)
  constants.py           # Константы
  stats.py               # Статистика расписания
  costs.py               # Модель стоимости смен по ТК РФ
  validation.py          # Валидация конфигурации
  xls_import.py          # Импорт carry-over из XLS
  scheduler/             # Ядро генерации расписания
    core.py              # Greedy-алгоритм с backtracking
    solver.py            # CP-SAT solver (Google OR-Tools)
    greedy.py            # Построение одного дня
    constraints.py       # Проверка ограничений
    changelog.py         # Лог изменений постпроцессинга
    multimonth.py        # Многомесячная генерация
    postprocess/         # Постпроцессинг (12 проходов)
  export/
    xls.py               # Экспорт в Excel
    ics.py               # Экспорт в iCalendar
    pdf.py               # Экспорт в PDF
  api/                   # REST API (FastAPI)
    routes/              # Эндпоинты
    auth.py              # Аутентификация
    ratelimit.py         # Rate limiting
    schemas.py           # Request/Response модели
    settings.py          # Конфигурация API
    whatif_service.py    # What-if сервис
  ui/                    # Streamlit UI компоненты
app.py                   # Точка входа Streamlit
api_main.py              # Точка входа FastAPI
config.example.yaml      # Пример конфигурации
Dockerfile               # Docker-образ
docker-compose.yml       # dev, staging, api сервисы
```

## Локальный Docker

Для разработки и тестирования без установки Python:

```bash
docker compose up dev       # разработка с hot-reload (порт 8501)
docker compose up staging   # staging-like сборка (порт 8502)
docker compose up api       # REST API (порт 8000)
```

- `dev`: монтирует `app.py`, `src/`, `config.example.yaml` — изменения видны сразу (Streamlit auto-reload). Логирование на уровне `DEBUG`
- `staging`: собранный образ без монтирования — для проверки перед мержем
- `api`: FastAPI + Uvicorn, логирование на уровне `INFO`
- Все сервисы stateless, БД не требуется

### Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DUTY_LOG_LEVEL` | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DUTY_LOG_FILE` | Путь к файлу лога (опционально, RotatingFileHandler) |
| `DUTY_API_AUTH_ENABLED` | Включить аутентификацию API |
| `DUTY_API_KEYS` | API-ключи через запятую |
| `DUTY_API_RATE_LIMIT` | Лимит запросов (по умолчанию `60/minute`) |

## Branch Protection

| Ветка | PR обязателен | Ревью | CI checks | Force push |
|-------|:---:|:---:|-----------|:---:|
| `dev` | Да | 0 | lint, unit-tests, smoke | Нет |
| `test` | Да | 1 | Все ci-test jobs | Нет |
| `main` | Да | 1 + env approval | Все ci-main jobs | Нет |

Настройка через GitHub Settings → Branches → Branch protection rules:
- **main/test**: Required status checks, Require PR before merging, Dismiss stale reviews, Restrict force-push.

## Rollback

### Откат тега (релиз не опубликован — удаление draft)

```bash
gh release delete vX.Y.Z --yes
git push origin --delete vX.Y.Z
git tag --delete vX.Y.Z
```

### Откат опубликованного релиза

```bash
git revert <merge-commit-sha>
git push origin dev
```

Затем провести через `dev → test → main` как обычный PR. После мержа `ci-tag.yml` создаст новый тег с инкрементированной патч-версией.

### Переустановка предыдущего wheel

```bash
pip install "duty-schedule==X.Y.Z"
```

Все wheel доступны на странице GitHub Releases. SHA256-контрольные суммы — в `checksums.txt` рядом с артефактами.

### Отмена мержа PR в main

```bash
gh pr revert <PR-number>
```

После revert-PR провести через CI как обычно. Cherry-pick в `dev` и `test`:

```bash
git cherry-pick <revert-commit-sha>
git push origin dev test
```

# Руководство по вкладу в проект

## Начало работы

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync --dev
```

## Ветвление и workflow

Проект использует трёхуровневый pipeline:

```
feature/xyz ──PR──> dev ──PR──> test ──PR──> main
```

| Ветка | Назначение | CI |
|-------|-----------|-----|
| `dev` | Интеграция фич, быстрая проверка | ci-dev.yml (~3 мин) |
| `test` | Стабилизация, расширенное тестирование | ci-test.yml (~8 мин) |
| `main` | Production, полная регрессия | ci-main.yml (~15 мин) |

### Создание фичи

1. Создать ветку от `dev`: `git checkout -b feature/my-feature dev`
2. Разработка и коммиты
3. PR в `dev` — проходит lint + unit + smoke
4. PR из `dev` в `test` — проходит полный набор тестов + security + performance
5. PR из `test` в `main` — полная регрессия + UI + system тесты

### Hotfix

Для критических исправлений:

1. Ветка от `main`: `git checkout -b hotfix/critical-fix main`
2. PR напрямую в `main` — проходит полную регрессию ci-main.yml
3. После мержа — cherry-pick в `dev` и `test`

## Стиль кода

- Python 3.12+
- Форматтер: `ruff format`
- Линтер: `ruff check` — все правила из `pyproject.toml`
- Типизация: `mypy` (проверяется в ci-test и ci-main)

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Тесты

```bash
# Все тесты
uv run pytest

# По уровням
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/contract
uv run pytest tests/system

# С покрытием
uv run pytest --cov=duty_schedule --cov-report=term-missing

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
  e2e/            # End-to-end (CLI workflow, Streamlit API)
  performance/    # Бенчмарки (pytest-benchmark)
  system/         # Системные (бизнес-правила, детерминированность)
  ui/             # UI тесты (Playwright + Streamlit)
```

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
3. При мерже в `main` — `ci-deploy.yml` автоматически создаёт tag `vX.Y.Z`
4. Tag запускает `release.yml` → GitHub Release

## Dependency Groups

```bash
uv sync --dev                           # базовые dev-зависимости
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
src/duty_schedule/    # Основной код
tests/                # Тесты (unit, integration, contract, e2e, performance, system, ui)
examples/             # Примеры конфигурации
.github/workflows/    # CI/CD (ci-dev, ci-test, ci-main, ci-deploy, release)
.github/actions/      # Переиспользуемые composite actions
```

## Branch Protection

| Ветка | PR обязателен | Ревью | CI checks | Force push |
|-------|:---:|:---:|-----------|:---:|
| `dev` | Да | 0 | lint, unit-tests, smoke | Нет |
| `test` | Да | 1 | Все ci-test jobs | Нет |
| `main` | Да | 1 + env approval | Все ci-main jobs | Нет |

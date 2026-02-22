# Руководство по вкладу в проект

## Начало работы

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync --dev
```

## Ветвление и разработка

Проект использует **trunk-based development**:

- Основная ветка: `main` (защищена)
- Фичи разрабатываются в коротких ветках: `feature/<описание>`
- PR должны проходить CI полностью перед слиянием
- Линтинг: `ruff` (без ошибок)
- Покрытие тестами: ≥ 80%

## Стиль кода

- Python 3.12+
- Форматтер: `ruff format`
- Линтер: `ruff check` — все правила из `pyproject.toml`
- Типизация: аннотации типов обязательны для публичных функций
- Docstrings: на русском языке

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Тесты

```bash
# Все тесты
uv run pytest

# Только unit
uv run pytest tests/unit

# Только интеграционные
uv run pytest tests/integration

# С покрытием
uv run pytest --cov=duty_schedule --cov-report=term-missing
```

Минимальное покрытие: **80%**. CI завершится с ошибкой при меньшем значении.

## Версионирование

Проект использует [семантическое версионирование](https://semver.org/lang/ru/):

- `MAJOR.MINOR.PATCH`
- PATCH — исправление ошибок
- MINOR — новые возможности без breaking changes
- MAJOR — несовместимые изменения API

Версия хранится в `src/duty_schedule/__init__.py` и `pyproject.toml`.

## Процесс релиза

1. Обновить версию в `src/duty_schedule/__init__.py` и `pyproject.toml`
2. Создать PR → merge в `main`
3. Создать тег: `git tag v1.2.3 && git push origin v1.2.3`
4. GitHub Actions автоматически создаст Release

## Сообщения коммитов

Используйте [Conventional Commits](https://www.conventionalcommits.org/ru/):

```
feat: добавить поддержку часового пояса Владивостока
fix: исправить подсчёт ночных смен при отпуске
docs: обновить примеры конфигурации
test: добавить тест граничного случая с длинным отпуском
refactor: упростить алгоритм отката
```

## Структура проекта

```
src/duty_schedule/    # Основной код
tests/unit/           # Модульные тесты
tests/integration/    # Интеграционные тесты
docs/                 # Документация
examples/             # Примеры конфигурации
```

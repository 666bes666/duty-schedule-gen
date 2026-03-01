# Генератор графика дежурств

Инструмент для автоматического составления месячного графика дежурств с круглосуточным покрытием (24/7).

Доступен в двух режимах: **веб-интерфейс** (рекомендуется) и **CLI**.

## Быстрый старт

**→ [Подробная инструкция по установке для всех ОС](УСТАНОВКА.md)** _(для тех, кто не работал с терминалом)_

**Для тех, кто знаком с терминалом:**
```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync && uv pip install -e ".[web]"

# Веб-интерфейс
uv run streamlit run app.py

# Или через лончер (двойной клик)
# macOS:   launchers/start-macos.command
# Windows: launchers/start-windows.bat
# Linux:   launchers/start-linux.sh
```

## Возможности

- Генерация оптимального расписания на месяц с покрытием трёх смен (утро, вечер, ночь) каждый день
- Учёт официального российского производственного календаря (через [isdayoff.ru](https://isdayoff.ru))
- Поддержка сотрудников из Москвы и Хабаровска с разными типами графика (гибкий / 5/2)
- Экспорт в `.xlsx` (цветовое кодирование смен, совместимость с Excel 2016+)
- Экспорт в `.ics` (отдельные файлы для каждого типа смены)
- Детерминированная генерация через фиксированный seed
- Минимизация изолированных выходных для FLEXIBLE-сотрудников
- Структурированное логирование в JSON

## Веб-интерфейс (Streamlit)

Удобный браузерный интерфейс — заполните таблицу сотрудников и скачайте готовый XLS.

```bash
uv pip install -e ".[web]"
uv run streamlit run app.py
# Открыть в браузере: http://localhost:8501
```

Или запустить двойным кликом через лончеры из папки `launchers/`.
Подробнее — [УСТАНОВКА.md](УСТАНОВКА.md).

## Установка (CLI)

### Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов

### Из исходников

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync
```

### Запуск

```bash
uv run duty-schedule --help
```

## Использование

### Генерация расписания

```bash
uv run duty-schedule generate examples/config.yaml
```

С указанием директории вывода:

```bash
uv run duty-schedule generate examples/config.yaml --output-dir ./output
```

Только XLS:

```bash
uv run duty-schedule generate examples/config.yaml --format xls
```

С указанием праздников вручную (если API недоступен):

```bash
uv run duty-schedule generate examples/config.yaml --holidays "2025-03-08,2025-03-10"
```

### Проверка конфигурации

```bash
uv run duty-schedule validate examples/config.yaml
```

### Версия

```bash
uv run duty-schedule version
```

## Формат конфигурации

```yaml
month: 3
year: 2025
timezone: Europe/Moscow
seed: 42

employees:
  - name: "Иванов Иван Иванович"
    city: moscow
    schedule_type: flexible
    on_duty: true
    morning_only: false
    evening_only: false
    vacations:
      - start: "2025-03-10"
        end: "2025-03-15"
```

### Правила конфигурации

| Параметр | Описание |
|----------|----------|
| `city` | `moscow` или `khabarovsk` |
| `schedule_type` | `flexible` — любые дни; `5/2` — только будни |
| `on_duty` | Участвует в ротации смен (утро/вечер/ночь) |
| `morning_only` | Только утренние смены |
| `evening_only` | Только вечерние смены |
| `vacations` | Список периодов отпуска |

### Ограничения

- Минимум **4 дежурных** в Москве
- Минимум **2 дежурных** в Хабаровске
- `morning_only` и `evening_only` нельзя указывать одновременно

## Типы смен

| Смена | Время (МСК) | Цвет в XLS |
|-------|-------------|------------|
| Утро | 08:00–17:00 | Янтарный |
| Вечер | 15:00–00:00 | Тёмно-синий |
| Ночь | 00:00–08:00 | Фиолетовый |
| Рабочий день | 09:00–18:00 | Бирюзовый |
| Выходной | — | Серый |

## Разработка

```bash
# Установка зависимостей для разработки
uv sync --dev

# Линтинг
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Тесты
uv run pytest

# Тесты с покрытием
uv run pytest --cov=duty_schedule --cov-report=html
```

## CI/CD

Проект использует GitHub Actions:

- **CI** (`ci.yml`): запускается при каждом push и PR — линтинг, unit-тесты, интеграционные тесты, покрытие ≥ 80%
- **Release** (`release.yml`): при публикации тега `v*.*.*` — сборка wheel и создание GitHub Release

## Архитектура

Подробная документация: [`docs/architecture.md`](docs/architecture.md)

## Лицензия

MIT

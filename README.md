# Генератор графика дежурств

Инструмент для автоматического составления месячного графика дежурств с круглосуточным покрытием (24/7).

Доступен в трёх режимах: **веб-интерфейс** (рекомендуется), **CLI** и **REST API**.

## Быстрый старт

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync

# Веб-интерфейс
uv run streamlit run app.py
# Открыть в браузере: http://localhost:8501
```

Для CP-SAT solver (оптимальная генерация через Google OR-Tools):

```bash
uv sync --extra solver
```

### Docker (альтернатива)

Не требует установки Python — всё собирается в контейнере.

```bash
docker compose up dev
# Открыть в браузере: http://localhost:8501
```

Доступные сервисы:

| Сервис | Порт | Назначение |
|--------|------|------------|
| `dev` | 8501 | Streamlit с hot-reload, debug-логирование |
| `staging` | 8502 | Собранный образ без монтирования — проверка перед мержем |
| `api` | 8000 | REST API (FastAPI + Uvicorn) |

```bash
docker compose up dev       # разработка
docker compose up staging   # staging
docker compose up api       # REST API
```

Сервис `dev` монтирует `app.py`, `src/` и `config.example.yaml` — изменения видны сразу через Streamlit auto-reload. Все сервисы stateless, БД не требуется.

## Возможности

- Генерация оптимального расписания на месяц с покрытием трёх смен (утро, вечер, ночь) каждый день
- Два алгоритма: **greedy** (быстрый, по умолчанию) и **CP-SAT** (оптимальный, через Google OR-Tools)
- Учёт официального российского производственного календаря (через [isdayoff.ru](https://isdayoff.ru))
- Поддержка сотрудников из Москвы и Хабаровска с разными типами графика (гибкий / 5/2)
- Экспорт в `.xlsx` (цветовое кодирование смен, статистика, подсчёт часов, совместимость с Excel 2016+)
- Экспорт в `.ics` — персональные календари для каждого сотрудника с учётом часовых поясов
- Экспорт в **PDF** для печати на стену
- Многомесячная генерация с автоматическим carry-over между месяцами
- What-if анализ: сравнение сценариев «что если изменить параметры»
- Детерминированная генерация через фиксированный seed
- Многоэтапный постпроцессинг: минимизация изолированных выходных, выравнивание нагрузки, балансировка вечерних смен
- Интерактивные Altair-графики: структура смен, норма vs факт, покрытие по дням, выходные/праздники
- Метрики баланса: σ нагрузки, σ выходных, σ ночных — для оценки справедливости графика
- Подсчёт часов в XLS (8 ч / 7 ч сокращённый день) с моделью стоимости по ТК РФ
- Лимиты однотипных дежурных смен подряд (утро / вечер / рабочий день)
- Группы сотрудников — не более одного дежурного из одной группы на смене
- Фиксированные назначения (pins) — закрепление конкретного сотрудника на конкретный день и смену
- Импорт carry-over из XLS предыдущего месяца (автоопределение состояния на стыке месяцев)
- REST API с аутентификацией, rate-limiting и what-if эндпоинтами
- Структурированное JSON-логирование (structlog) с настройкой уровня через переменные окружения

## Веб-интерфейс (Streamlit)

Браузерный интерфейс — заполните таблицу сотрудников и скачайте готовый XLS.

```bash
uv run streamlit run app.py
# Открыть в браузере: http://localhost:8501
```

Возможности UI:

- Редактор сотрудников с массовым редактированием
- Загрузка/выгрузка конфигурации в YAML
- Импорт carry-over из XLS предыдущего месяца
- Фиксация назначений (pins) на конкретные дни
- Редактирование сгенерированного расписания с live-валидацией
- Сравнение версий расписания (история изменений)
- What-if симуляция: анализ влияния изменений параметров

Вкладки результата:

- **Календарь** — расписание в виде таблицы, строки отсортированы по городу, признаку дежурства, типу графика и имени
- **Нагрузка** — интерактивная аналитика: метрики баланса (σ), структура смен, норма vs факт, покрытие по дням с разбивкой по типам смен, нагрузка в выходные/праздники (Altair)
- **Экспорт** — скачать XLS, персональный `.ics` для каждого сотрудника, PDF

## Установка (CLI)

### Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов

### Из исходников

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
uv sync            # базовая установка
uv sync --extra solver  # + CP-SAT solver (опционально)
```

### Запуск

```bash
uv run duty-schedule --help
```

## Использование

### Генерация расписания

```bash
uv run duty-schedule generate config.example.yaml
```

С указанием директории вывода:

```bash
uv run duty-schedule generate config.example.yaml --output-dir ./output
```

Только XLS:

```bash
uv run duty-schedule generate config.example.yaml --format xls
```

С указанием праздников вручную (если API недоступен):

```bash
uv run duty-schedule generate config.example.yaml --holidays "2025-03-08,2025-03-10"
```

С переопределением seed:

```bash
uv run duty-schedule generate config.example.yaml --seed 123
```

### Генерация на несколько месяцев

```bash
uv run duty-schedule generate-range config.example.yaml --start 01.2025 --end 06.2025
```

Автоматически пробрасывает carry-over между месяцами.

### Проверка конфигурации

```bash
uv run duty-schedule validate config.example.yaml
```

### Версия

```bash
uv run duty-schedule version
```

## REST API

FastAPI-сервер для программного взаимодействия.

### Запуск

```bash
uv run uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload
```

Или через Docker:

```bash
docker compose up api
```

### Конфигурация

Через переменные окружения или `.env` файл (см. `.env.example`):

| Переменная | Описание | По умолчанию |
|------------|----------|-------------|
| `DUTY_API_AUTH_ENABLED` | Включить аутентификацию по API-ключу | `false` |
| `DUTY_API_KEYS` | API-ключи через запятую | — |
| `DUTY_API_RATE_LIMIT` | Лимит запросов | `60/minute` |

### Эндпоинты

- `POST /schedule/generate` — генерация расписания
- `POST /whatif/compare` — what-if сравнение сценариев
- `GET /holidays/{year}/{month}` — производственный календарь
- `POST /config/validate` — валидация конфигурации
- `POST /export/xls` — экспорт в XLS

Документация Swagger: `http://localhost:8000/docs`

## Формат конфигурации

```yaml
month: 3
year: 2025
timezone: Europe/Moscow
seed: 42
solver: greedy  # или cpsat

employees:
  - name: "Иванов Иван"
    city: moscow
    schedule_type: flexible
    on_duty: true
    morning_only: false
    evening_only: false
    max_consecutive_working: 5
    vacations:
      - start: "2025-03-10"
        end: "2025-03-15"

pins:
  - date: "2025-03-01"
    employee_name: "Иванов Иван"
    shift: morning
```

### Параметры сотрудника

| Параметр | Описание | По умолчанию |
|----------|----------|-------------|
| `name` | Имя сотрудника | — |
| `city` | `moscow` или `khabarovsk` | — |
| `schedule_type` | `flexible` — любые дни; `5/2` — только будни | — |
| `on_duty` | Участвует в ротации смен (утро/вечер/ночь) | `true` |
| `morning_only` | Только утренние смены | `false` |
| `evening_only` | Только вечерние смены | `false` |
| `max_consecutive_working` | Максимум рабочих дней подряд | `5` |
| `vacations` | Список периодов отпуска | `[]` |
| `unavailable_dates` | Список дат недоступности | `[]` |
| `days_off_weekly` | Постоянные выходные дни недели (0=Пн, 6=Вс) | `[]` |
| `team_lead` | Признак тимлида | `false` |
| `preferred_shift` | Предпочтительная смена | — |

### Параметры конфигурации

| Параметр | Описание | По умолчанию |
|----------|----------|-------------|
| `solver` | Алгоритм: `greedy` или `cpsat` | `greedy` |
| `pins` | Фиксированные назначения | `[]` |
| `carry_over` | Перенос состояния с предыдущего месяца | `[]` |

### Ограничения

- Минимум **4 дежурных** в Москве
- Минимум **2 дежурных** в Хабаровске
- `morning_only` и `evening_only` нельзя указывать одновременно

## Типы смен

| Смена | Время (МСК) | Цвет в XLS |
|-------|-------------|------------|
| Утро | 08:00–17:00 | Янтарный |
| Вечер | 15:00–00:00 | Индиго |
| Ночь | 00:00–08:00 | Лавандовый |
| Рабочий день | 09:00–18:00 | Бирюзовый |
| Выходной | — | Серый |

## Логирование

Структурированное JSON-логирование через structlog.

| Переменная | Описание | По умолчанию |
|------------|----------|-------------|
| `DUTY_LOG_LEVEL` | Уровень: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `DUTY_LOG_FILE` | Путь к файлу лога (RotatingFileHandler, 10 МБ) | — (только stderr) |

```bash
DUTY_LOG_LEVEL=DEBUG uv run duty-schedule generate config.example.yaml
```

В Docker уровень задан через `docker-compose.yml`: `DEBUG` для dev, `INFO` для api.

## Разработка

```bash
uv sync --dev

uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
uv run pytest tests/ -q --ignore=tests/ui
```

Подробнее: [`CONTRIBUTING.md`](CONTRIBUTING.md)

## CI/CD

Трёхуровневый pipeline через GitHub Actions:

| Ветка | Workflow | Проверки |
|-------|----------|----------|
| dev | ci-dev.yml | lint, unit+integration, smoke |
| test | ci-test.yml | + mypy, 4 платформы, security, performance |
| main | ci-main.yml | + 6 платформ, UI/Playwright, system, e2e, build |

При изменении версии в `pyproject.toml` на main — автоматический tag и GitHub Release.

## Архитектура

Подробная документация: [`ARCHITECTURE.md`](ARCHITECTURE.md)

## Лицензия

MIT

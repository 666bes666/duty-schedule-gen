# Архитектура системы

## Обзор

```
┌─────────────────────────────────────────────────────┐
│                  CLI (Typer)                         │
│           duty_schedule/cli.py                       │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   ┌─────────────┐ ┌──────────┐ ┌───────────────────┐
   │  calendar.py │ │scheduler │ │   export/          │
   │             │ │  .py     │ │  ├── xls.py        │
   │ isdayoff.ru │ │          │ │  └── ics.py        │
   └─────────────┘ └──────────┘ └───────────────────┘
          │            │
          ▼            ▼
   ┌──────────────────────┐
   │      models.py       │
   │  Employee, Config,   │
   │  Schedule, ...       │
   └──────────────────────┘
```

## Компоненты

### `cli.py` — Точка входа

Typer-приложение с тремя командами:
- `generate` — основная команда
- `validate` — проверка конфигурации
- `version` — версия приложения

### `models.py` — Модели данных

Pydantic v2 модели с встроенной валидацией:
- `Employee` — сотрудник с атрибутами и отпусками
- `Config` — полная конфигурация (месяц, сотрудники, seed)
- `DaySchedule` — расписание одного дня
- `Schedule` — полный месяц + метаданные

### `calendar.py` — Производственный календарь

- Загружает данные из `isdayoff.ru/api/getdata`
- Возвращает `set[date]` — даты выходных и праздников
- При ошибке API: ручной ввод через `--holidays` или только выходные

### `scheduler.py` — Движок планирования

Жадный алгоритм с откатом:

```
for day in month:
    Phase 1: Ночная смена (Хабаровск, обязательно)
    Phase 2: Утро + Вечер (Москва, обязательно)
    Phase 3: Рабочий день (не-дежурные)
    Phase 4: Принудительное назначение при 3+ выходных подряд
    → update state
    if fail: backtrack up to 3 days
```

### `export/xls.py` — Excel экспорт

- openpyxl с цветовым кодированием
- Строки = даты, столбцы = типы смен
- Совместим с Excel 2016+

### `export/ics.py` — iCalendar экспорт

- 4 отдельных ICS файла (по типу смены)
- RFC 5545 совместимый формат
- Корректная обработка часовых поясов

## Поток данных

```
config.yaml
    │
    ▼
Config (Pydantic)
    │
    ├──► fetch_holidays() → set[date]
    │
    └──► generate_schedule(config, holidays)
              │
              ▼
         Schedule
              │
         ┌───┴────────┐
         ▼            ▼
    export_xls()  export_ics()
         │            │
         ▼            ▼
  schedule.xlsx  *.ics files
```

## Хранение состояния планировщика

```python
@dataclass
class EmployeeState:
    consecutive_working: int    # подряд рабочих дней
    consecutive_off: int        # подряд выходных
    last_shift: ShiftType       # последняя смена (для правил отдыха)
    night_count: int            # всего ночных смен
    morning_count: int
    evening_count: int
    workday_count: int
    total_working: int
```

## Правила справедливости

1. **Ночные смены**: распределяются между хабаровскими сотрудниками с минимальным числом смен
2. **Утро/вечер**: распределяются по числу смен (чем меньше — тем приоритетнее)
3. **Разница**: максимум 1 смена каждого типа между сотрудниками с одинаковыми атрибутами
4. **Вечерние смены**: разница max−min ≤ 1

## Алгоритм отката

При невозможности построить расписание на день:
1. Откат на 1–3 предыдущих дня
2. Пересев RNG (seed + attempts × 1000 + day_idx)
3. Повторная попытка
4. После 10 попыток — ошибка с объяснением

## Конфигурация CI/CD

```
push/PR → ci.yml:
  lint → ruff check + ruff format --check
  test → pytest unit + integration (ubuntu + windows)
  coverage → ≥ 80%
  build → smoke test duty-schedule --help

tag v*.*.* → release.yml:
  uv build → wheel + sdist
  gh release create → GitHub Release
```

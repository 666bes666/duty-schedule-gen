# Архитектура и логика duty-schedule-gen

> Полное описание системы для воспроизведения с нуля. Актуально на момент релиза v1.5.0.

---

## 1. Назначение

Генератор дежурных расписаний для распределённой команды двух городов (Москва и Хабаровск).

**Задача:** на каждый календарный месяц автоматически распределить дежурные смены и рабочие дни между сотрудниками с учётом:
- производственного календаря РФ (праздники и выходные через isdayoff.ru)
- индивидуальных ограничений сотрудников (тип графика, отпуска, лимиты смен)
- равномерности нагрузки
- предпочтений по паттерну выходных дней (пары consecutive off-days)

---

## 2. Технический стек

| Слой | Технология |
|---|---|
| UI | Streamlit (app.py) |
| Алгоритм | Python 3.12+, чистый алгоритм (без внешних солверов) |
| Модели данных | Pydantic v2 |
| CLI | Typer |
| Экспорт | openpyxl (XLS), icalendar (ICS) |
| HTTP-клиент | httpx |
| Логирование | structlog |
| Менеджер пакетов | uv |
| Тесты | pytest |
| Деплой | Yandex Cloud Serverless Containers + GitHub Actions |

---

## 3. Структура проекта

```
duty-schedule-gen/
├── app.py                        # Streamlit UI (точка входа веб-приложения)
├── src/duty_schedule/
│   ├── models.py                 # Pydantic-модели данных
│   ├── scheduler.py              # Ядро: генерация расписания
│   ├── calendar.py               # Загрузка праздников (isdayoff.ru)
│   ├── cli.py                    # CLI (Typer)
│   ├── logging.py                # Настройка structlog
│   └── export/
│       ├── xls.py                # Экспорт в Excel
│       └── ics.py                # Экспорт в ICS (iCalendar)
├── tests/
│   ├── unit/                     # Юнит-тесты (ограничения, утилиты)
│   └── integration/              # Интеграционные тесты (полная генерация)
├── pyproject.toml                # Зависимости и настройки инструментов
└── ARCHITECTURE.md               # Этот файл
```

---

## 4. Модели данных (`models.py`)

### 4.1 Перечисления

```python
ScheduleType: FLEXIBLE | FIVE_TWO
ShiftType:    MORNING | EVENING | NIGHT | WORKDAY | DAY_OFF | VACATION
City:         MOSCOW | KHABAROVSK
```

**Смены:**
- `MORNING` — утренняя дежурная смена 08:00–17:00 (только Москва)
- `EVENING` — вечерняя дежурная смена 15:00–00:00 (только Москва)
- `NIGHT`   — ночная дежурная смена 00:00–08:00 (только Хабаровск)
- `WORKDAY` — обычный рабочий день 09:00–18:00 (не дежурная смена)
- `DAY_OFF` — выходной день
- `VACATION`— отпуск

### 4.2 Employee

| Поле | Тип | Описание |
|---|---|---|
| `name` | str | Уникальное имя |
| `city` | City | Москва или Хабаровск |
| `schedule_type` | ScheduleType | `FLEXIBLE` (скользящий) или `FIVE_TWO` (Пн–Пт) |
| `on_duty` | bool | Является ли дежурным (участвует в сменах) |
| `always_on_duty` | bool | Всегда на дежурстве, никогда не пропускает (только Москва) |
| `morning_only` | bool | Работает только утренние смены |
| `evening_only` | bool | Работает только вечерние смены |
| `vacations` | list[VacationPeriod] | Периоды отпуска |
| `unavailable_dates` | list[date] | Конкретные даты недоступности |
| `max_morning_shifts` | int? | Лимит утренних смен в месяц |
| `max_evening_shifts` | int? | Лимит вечерних смен в месяц |
| `max_night_shifts` | int? | Лимит ночных смен в месяц |
| `preferred_shift` | ShiftType? | Мягкое предпочтение типа смены |
| `workload_pct` | int (1–100) | Доля ставки (100 = полная) |
| `days_off_weekly` | list[int] | Постоянные выходные дни недели (0=Пн) |
| `max_consecutive_working` | int? | Персональный лимит рабочих дней подряд |
| `group` | str? | Группа: двое из одной группы не назначаются на одну смену |

### 4.3 Config

```python
Config(
    month=3, year=2026, seed=42,
    employees=[...],
    pins=[PinnedAssignment(...)],   # Зафиксированные назначения
    carry_over=[CarryOverState(...)], # Перенос состояния с пред. месяца
    timezone="Europe/Moscow",
)
```

**CarryOverState** — переносит `consecutive_working`, `consecutive_off`, `last_shift` с конца предыдущего месяца, чтобы ограничения корректно работали в начале нового.

### 4.4 DaySchedule / Schedule

```python
DaySchedule(
    date=..., is_holiday=...,
    morning=["Имя"],   # Утренняя смена
    evening=["Имя"],   # Вечерняя смена
    night=["Имя"],     # Ночная смена
    workday=["А", "Б"],# Обычный рабочий день
    day_off=["В"],     # Выходной
    vacation=["Г"],    # Отпуск
)
```

`DaySchedule.is_covered()` → True, если все три обязательные смены (morning, evening, night) заполнены хотя бы одним человеком.

---

## 5. Алгоритм генерации расписания (`scheduler.py`)

### 5.1 Ключевые константы

```python
MAX_CONSECUTIVE_WORKING      = 5   # Макс. рабочих дней подряд (жёсткий лимит)
MAX_CONSECUTIVE_WORKING_FLEX = 6   # Допустимо в постобработке для гибких дежурных
MAX_CONSECUTIVE_OFF          = 3   # Макс. выходных подряд
MIN_WORK_BETWEEN_OFFS        = 3   # Мин. рабочих смен между блоками выходных
MAX_BACKTRACK_DAYS           = 3   # Глубина отката при ошибке
MAX_BACKTRACK_ATTEMPTS       = 10  # Макс. число откатов
```

### 5.2 Вспомогательные функции

- `_max_cw(emp)` — жёсткий лимит рабочих дней подряд для сотрудника (учитывает `max_consecutive_working`; 5 по умолчанию)
- `_max_cw_postprocess(emp)` — лимит для постобработки: 6 для `FLEXIBLE on_duty` (не duty_only), иначе 5
- `_max_co(emp)` — макс. выходных подряд (3 для всех)
- `_duty_only(emp)` — True если `on_duty AND (morning_only OR evening_only OR always_on_duty)`: такой сотрудник работает только дежурными сменами, никогда WORKDAY
- `_can_work(emp, state, day, holidays)` — может ли сотрудник работать в день: не в отпуске/недоступен, не достиг `_max_cw`, для `FIVE_TWO` — не выходной/праздник
- `_resting_after_evening(state)` — True если последняя смена была EVENING: следующий день запрещены MORNING и WORKDAY (слишком мало отдыха)
- `_resting_after_night(state)` — True если последняя смена NIGHT

### 5.3 EmployeeState

Изменяемое состояние, обновляется при каждом назначении через `state.record(shift)`:

```python
EmployeeState(
    consecutive_working=0,  # дней рабочих подряд
    consecutive_off=0,      # дней выходных подряд
    last_shift=None,        # последняя смена
    total_working=0,        # всего рабочих дней в месяце
    target_working_days=0,  # норма (из произв. календаря * workload_pct)
    vacation_days=0,        # дней отпуска в рабочие дни
    night/morning/evening/workday_count,  # счётчики смен
)
```

`state.needs_more_work(remaining_days)` → True если текущий дефицит относительно нормы требует работы (с учётом оставшихся дней).

`state.effective_target` → `target_working_days - vacation_days`.

### 5.4 Жадный алгоритм с откатом (`generate_schedule`)

```
while day_idx < len(all_days):
    try:
        ds = _build_day(day, ...)
        days.append(ds)
        day_idx += 1
    except ScheduleError:
        откат на MAX_BACKTRACK_DAYS шагов назад
        пересев RNG
        total_backtracks++
        if total_backtracks > MAX_BACKTRACK_ATTEMPTS: raise
```

**Откат** происходит когда `_build_day` не может покрыть обязательную смену (нет доступных сотрудников). Откат возвращает состояния и RNG на несколько дней назад, давая алгоритму другой случайный выбор.

### 5.5 Построение одного дня: `_build_day`

Порядок назначений внутри одного дня:

**1. always_on_duty сотрудники** (Москва)
Первыми фиксируются сотрудники с `always_on_duty=True` — они всегда работают кроме случаев блокировки.

**2. Ночная смена** (Хабаровск)
Выбор 1 сотрудника из `khabarovsk_duty`. Приоритет: дефицит смен (`needs_more_work`), затем минимальное количество ночных смен (`_select_for_mandatory` → `_select_fair`).

**3. Утренняя смена** (Москва)
Выбор 1 сотрудника из `moscow_duty`. Если есть `morning_only`, они имеют приоритет (при наличии хотя бы одного evening-capable снаружи группы).

**4. Вечерняя смена** (Москва)
Выбор 1 сотрудника из оставшихся:
- Если есть сотрудники, которым нужно продолжить вечернюю серию (`_resting_after_evening`) — они приоритетны
- Иначе: предпочтение гибким дежурным с `consecutive_working >= MIN_WORK_BETWEEN_OFFS - 1 = 2` (чтобы вечер не попадал в начало рабочей серии, создавая изолированный рабочий день)
- Если таких нет — стандартный выбор по `_select_for_mandatory`

> **Правило вечерней смены:** после вечерней смены (00:00 окончание) следующий день сотрудник не может работать утреннюю или WORKDAY смену — недостаточно времени отдыха. Он может получить только ещё одну вечернюю или выходной.

**5. Дополнительные WORKDAY** (только Москва, только не-праздник)
Сотрудники без назначения добавляются в цикле до тех пор, пока есть желающие работать:
- не `_duty_only`
- `needs_more_work(remaining_days)` = True
- `consecutive_working < _max_cw(e) = 5`
- не `_resting_after_evening`
- не `FLEXIBLE AND consecutive_off == 1` (не начинать работу после 1-го дня выходного, чтобы сформировать пару)

При `_next_is_holiday`: перед добавлением WORKDAY проверяется, что завтра будет достаточно доступных сотрудников для покрытия смен.

**6. Хабаровск WORKDAY**
Для каждого хабаровского дежурного без смены:
- если `needs_more_work AND NOT (FLEXIBLE AND consecutive_off == 1)` → WORKDAY
- иначе → DAY_OFF

**7. Не-дежурные сотрудники (5/2)**
Выходной или WORKDAY по производственному календарю.

**8. Anti-isolated-off override**
После базового назначения: если сотрудник получил DAY_OFF, но `consecutive_off >= _max_co(emp) = 3` — форсировать WORKDAY (предотвращает блоки 4+ выходных). Условие: `_can_work`, не `_resting_after_evening`, `needs_more_work OR FLEXIBLE`, не праздник.

**9. Anti-short-work override**
После anti-isolated-off: если сотрудник FLEXIBLE получил DAY_OFF, но `0 < consecutive_working < MIN_WORK_BETWEEN_OFFS = 3` — форсировать WORKDAY. Нет исключения для праздников — предотвращает сценарий "1 рабочий день в праздник между двумя выходными".

---

## 6. Постобработочный pipeline

После жадной генерации выполняется pipeline из 5 функций:

```
generate:
 1. _balance_weekend_work         — баланс суббот/воскресений
 2. recalc states
 3. _balance_duty_shifts          — баланс утренних/вечерних/ночных смен
 4. _target_adjustment_pass       — подгонка под норму (1-й проход)
 5. _trim_long_off_blocks         — обрезка блоков 4+ выходных
 6. recalc states
 7. _target_adjustment_pass       — подгонка под норму (2-й проход)
 8. _minimize_isolated_off        — устранение изолированных выходных
 9. _break_evening_isolated_pattern — своп вечерних смен для устранения паттерна "вечер→отдых→изоляция"
10. _minimize_isolated_off        — повторный проход после свопов
11. _equalize_isolated_off        — выравнивание изолированных между сотрудниками
12. _minimize_isolated_off        — финальный проход
```

### 6.1 `_balance_weekend_work`

Выравнивает число суббот/воскресений между гибкими дежурными одного города. Разница max−min ≤ 1.

Механизм: swap в выходной день — перегруженный (A, на смене) меняется с недогруженным (B, на выходном). A уходит на WORKDAY, B принимает его дежурную смену.

Защита: не создаёт блоков выходных > `_max_co = 3`.

### 6.2 `_balance_duty_shifts`

Балансирует распределение утренних/вечерних/ночных смен между дежурными. Swap: перегруженный → WORKDAY, недогруженный → смена. Проверяет ограничения `_resting_after_evening`, `max_*_shifts`.

### 6.3 `_target_adjustment_pass`

Корректирует итоговое число рабочих дней каждого сотрудника до нормы.

**Избыток (actual > target):** снимает WORKDAY с конца месяца → DAY_OFF.
- Не снимает с праздников
- Не снимает с закреплённых (pinned) дней
- `_streak_around(working=False) <= _max_co(emp) = 3` — не создаёт блоки > 3
- Для FLEXIBLE full-time: не создаёт рабочие серии < `MIN_WORK_BETWEEN_OFFS = 3` с обеих сторон

**Недостача (actual < target):** добавляет WORKDAY с начала месяца → убирает из DAY_OFF.
- Не добавляет в праздники/выходные (производственный календарь)
- `_streak_around(working=True) <= _max_cw(emp) = 5` — не создаёт серии > 5
- Для FLEXIBLE: сортирует кандидатов, предпочитая изолированные выходные (те, что НЕ в off-блоке)

### 6.4 `_trim_long_off_blocks`

Для гибких дежурных (не duty_only): обрезает блоки выходных длиной > `_max_co(emp) = 3` (т.е. блоки ≥ 4).

Алгоритм для каждого блока ≥ 4:
1. Найти `trim_idx` в блоке: день без пина, не заблокированный, не после вечерней смены, не нарушит `_max_cw`
2. Найти `iso_i` — изолированный выходной вне блока, и его рабочего соседа `nb_i`
3. **Swap:** `trim_idx` (off→workday) + `nb_i` (workday→off) → блок уменьшается, изолированный становится парным
4. Если пары нет → тупо конвертировать `trim_idx` в workday (небольшой избыток корректирует 2-й `_target_adjustment_pass`)

### 6.5 `_minimize_isolated_off`

Устраняет изолированные выходные (окружённые рабочими днями с обеих сторон).

**Основной путь** (extend + compensate):
1. Найти `isolated_idx` — выходной, оба соседа которого рабочие
2. Для каждого рабочего соседа `extend_idx`:
   - Проверить: `consec_off_if_freed(extend_idx) <= _max_co = 3`
   - Найти `comp_i` — другой выходной для конвертации в WORKDAY (компенсация нормы)
     - Не из закреплённых дней
     - Для гибких: можно использовать выходные/праздники
     - `_consec_work_if_added(comp_i) <= _max_cw_postprocess(emp)` — для FLEXIBLE допускается до 6 рабочих дней подряд (чтобы устранить изолированный выходной)
     - Не создаёт новых изолированных выходных
   - Swap: `extend_idx` (workday→off), `comp_i` (off→workday)

**Fallback** (только для FLEXIBLE) — операция "переместить":
Если основной путь не нашёл компенсацию (нет подходящего comp_i):
1. Конвертировать `isolated_idx` в WORKDAY
2. Найти другой изолированный выходной `target_i` и его рабочего соседа `nb_i`
3. Конвертировать `nb_i` в DAY_OFF — теперь `target_i` + `nb_i` = пара
4. Эффект: изолированный выходной "исчезает" (становится рабочим), другой изолированный "склеивается" с соседним рабочим

Функция работает в цикле до стабилизации.

### 6.6 `_break_evening_isolated_pattern`

Устраняет изолированные выходные, вызванные паттерном "вечерняя смена → обязательный отдых → изолированный выходной".

**Механизм:** для каждого изолированного выходного, следующего за вечерней сменой, ищет другого сотрудника (не на выходном) и свопает вечернюю смену. Другой сотрудник берёт вечернюю, а исходный получает утреннюю/рабочую.

**Acceptance criteria:** принимаем своп, если emp_a (исходный) улучшился (`count_iso_after < count_iso_before`) И emp_b (получатель) остался в допустимых пределах (`count_iso_after <= 2`).

### 6.7 `_equalize_isolated_off`

Выравнивает число изолированных выходных между гибкими дежурными одного города.

**Механизм:** находит сотрудника с максимумом изолированных и сотрудника с минимумом, выполняет своп выходной↔рабочий день.

**Условие остановки:** разница `max - min <= 1` или `max <= 2`.

---

## 7. Вспомогательные функции алгоритма

### `_streak_around(emp_name, idx, days, working, carry_over_cw)`

Подсчитывает длину серии (рабочих или выходных) вокруг `days[idx]`, если этот день получает тип `working`. Учитывает `carry_over_cw` — перенос рабочих дней с предыдущего месяца.

### `_consec_work_if_added(emp_name, idx, days, carry_over_cw)`

Длина рабочей серии, если `days[idx]` становится рабочим. Используется для проверки `_max_cw` при добавлении компенсации в `_minimize_isolated_off`.

### `_select_fair(candidates, states, shift, rng, count)`

Выбрать `count` сотрудников: сортировка по минимальному числу смен данного типа, тайбрейк по `preferred_shift`, затем случайно.

### `_select_for_mandatory(candidates, states, shift, remaining_days, rng, count)`

Выбор для обязательных смен: сначала из тех, у кого дефицит нормы; если таких нет — из всех. Внутри — `_select_fair`.

### `_select_by_urgency(candidates, states, remaining_days, rng)`

Приоритет тем, у кого наибольший дефицит/оставшиеся дни (срочность). Используется в extra-workday цикле.

---

## 8. Правила расписания (бизнес-логика)

### Обязательные смены

Каждый день должен быть покрыт:
- ровно 1 утренняя (Москва)
- ровно 1 вечерняя (Москва)
- ровно 1 ночная (Хабаровск)

Минимальный состав команды: 4 дежурных в Москве, 2 в Хабаровске.

### Ограничения последовательностей

| Правило | Значение |
|---|---|
| Макс. рабочих дней подряд | 5 (жёстко в жадном алг.) / 6 (допустимо в постобработке для FLEXIBLE) |
| Макс. выходных подряд | 3 |
| Мин. рабочих дней между блоками выходных | 3 |
| После вечерней смены | Запрещены утренняя и WORKDAY на следующий день |

### Паттерн выходных для FLEXIBLE дежурных

Цель: максимально приближенный к 5/2 паттерн, но не привязанный к дням недели:
- Каждый блок выходных = **2 дня подряд** (предпочтительно) или 3 (допустимо)
- Перед выходными — **минимум 3 рабочих дня** подряд
- Алгоритм избегает изолированных (1-дневных) выходных

### Вечерняя смена и изоляция

**Правило-исключение:** вечерняя смена принципиально создаёт 1 рабочий день, если следующий день — выходной (из-за обязательного отдыха). Это архитектурное ограничение системы, намеренно сохраняемое. Алгоритм частично смягчает его, предпочитая назначать вечерние смены сотрудникам с `consecutive_working >= 2`.

### Нагрузка

- Каждый сотрудник должен отработать ровно `round(production_days * workload_pct / 100)` рабочих дней
- `production_days` = число рабочих дней в месяце по производственному календарю РФ
- Дни отпуска вычитаются из нормы

### Группы

Сотрудники с одинаковым `group` не назначаются на одну дежурную смену в один день.

---

## 9. Производственный календарь (`calendar.py`)

Источник: `https://isdayoff.ru/api/getdata?year=YYYY&month=MM&cc=ru`

Ответ: строка из 0 и 1 длиной `days_in_month`. `1` = нерабочий день (выходной или праздник).

Функции:
- `fetch_holidays(year, month)` — загружает праздники, возвращает `set[date]`
- `parse_manual_holidays(string, year, month)` — запасной вариант при недоступности API; формат: `YYYY-MM-DD,YYYY-MM-DD,...`
- `get_all_days(year, month)` — все даты месяца

---

## 10. Streamlit UI (`app.py`)

Одностраничное приложение с боковой панелью и основным полем.

### Боковая панель

- Выбор месяца/года
- Поле для ввода дат праздников (запасной вариант)
- Кнопка "Загрузить праздники" (isdayoff.ru)
- Seed генерации
- Перенос состояния с предыдущего месяца (carry_over)

### Основная область

- Таблица сотрудников (редактируемый DataFrame): имя, город, тип графика, флаги, лимиты
- Кнопка "Сгенерировать расписание"
- Отображение расписания в виде таблицы (дни × сотрудники)
- Кнопки экспорта: XLS (Excel) и ICS (iCalendar)

### Предзаполненная команда

По умолчанию заполняется реальная команда:
- **Москва:** Левченко (5/2, не дежурный), Хадзугов (5/2, не дежурный), Абашина (flexible, дежурная, предпочитает утро), Екат (5/2, always_on_duty, morning_only), Ищенко (flexible, дежурный), Пантелеймон (flexible, дежурный), Ужахов (flexible, дежурный)
- **Хабаровск:** Кочкин (5/2, не дежурный), Вика (flexible, дежурная), Голубев (flexible, дежурный), Карпенко (flexible, дежурный)

---

## 11. Экспорт (`export/`)

### Excel (`xls.py`)

Файл: `schedule_YYYY_MM.xlsx`

**Лист 1 — «График дежурств»:**
- Строки = сотрудники (сгруппированы: Москва → Хабаровск, дежурные → не-дежурные, 5/2 → гибкие)
- Столбцы = дни месяца
- Ячейки = тип смены (Утро / Вечер / Ночь / День / — / Отп)
- Цветовое кодирование каждого типа смены
- Праздники затемнены
- Столбец «Итого дней» — число рабочих дней

**Лист 2 — «Статистика»:**
- 17 столбцов метрик на каждого сотрудника:
  - Норма: Рабочих дней, Норма, ±Норма
  - Смены: Утро, Вечер, Ночь, День
  - Отдых: Выходных, Отпуск, Работал в выходные, Работал в праздники
  - Нагрузка: Макс. серия работы, Макс. серия отдыха, Изол. выходных, Сдвоен. выходных
- Цветовая индикация: ok (зелёный), warn (жёлтый), bad (оранжевый)
- Строка итогов по команде

**Лист 3 — «Легенда»:**
- Расшифровка цветов и обозначений смен

### ICS (`ics.py`)

Файл: `schedule_YYYY_MM.ics`

Генерирует iCalendar-события для каждого рабочего дня каждого сотрудника. Событие содержит имя сотрудника, тип смены, время начала/окончания (из `SHIFT_START`/`SHIFT_END`).

---

## 12. CLI (`cli.py`)

```bash
uv run duty-schedule generate --month 3 --year 2026 --output schedule.xlsx
```

Аргументы: `--month`, `--year`, `--seed`, `--holidays` (CSV строка дат), `--output` (путь к XLS).

---

## 13. Деплой

### Локально

```bash
uv run streamlit run app.py
```

### Yandex Cloud Serverless Containers

- Docker-образ → Yandex Container Registry
- Развёртывание через `yc serverless container revision deploy`
- GitHub Actions workflow: сборка → push → deploy при push в `main`
- URL: `https://bbal7kfrf454cvfhrnv1.containers.yandexcloud.net/`

---

## 14. Тесты

```bash
uv run pytest tests/ -q
```

| Категория | Файл | Что тестируется |
|---|---|---|
| Ограничения | `unit/test_constraints.py` | `_can_work`, `_is_weekend_or_holiday`, `_resting_after_evening` |
| Полная генерация | `integration/test_full_schedule.py` | Покрытие смен, отсутствие дублей, carry_over, XLS/ICS экспорт |
| Новые функции | `integration/test_new_features.py` | Пины, отпуска, `workload_pct`, `always_on_duty`, `group` |

---

## 15. Воспроизведение с нуля

```python
from duty_schedule.models import Config, Employee, City, ScheduleType
from duty_schedule.scheduler import generate_schedule
from duty_schedule.calendar import fetch_holidays

employees = [
    Employee(name="Иванов", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True),
    Employee(name="Петров", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True),
    Employee(name="Сидоров", city=City.MOSCOW, schedule_type=ScheduleType.FIVE_TWO, on_duty=True, morning_only=True, always_on_duty=True),
    Employee(name="Козлов", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True),
    Employee(name="Смирнов", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE, on_duty=True),
    Employee(name="Попов", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE, on_duty=True),
]

config = Config(month=3, year=2026, seed=42, employees=employees)
holidays = fetch_holidays(2026, 3)   # или set() для тестов
schedule = generate_schedule(config, holidays)

for day in schedule.days:
    print(day.date, "утро:", day.morning, "вечер:", day.evening, "ночь:", day.night)
```

Минимальный состав: 4 дежурных в Москве (из которых хотя бы 1 может работать утром и 1 — вечером) и 2 дежурных в Хабаровске.

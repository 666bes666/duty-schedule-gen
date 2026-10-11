# План: Составление графика в интерфейсе

## Технический контекст и конституция

Python 3.12+, uv, Pydantic 2, существующий scheduler/FastAPI/Streamlit/export.
Работа напрямую в dev; чужие изменения сохраняются, feature.json не меняется.
SPECIFY_FEATURE_DIRECTORY указывает на этот каталог; SPECIFY_FEATURE_NO_PERSIST=1.
Новая функциональность имеет тесты; покрытие >=80%; без # комментариев в исходниках.

## Реализация и границы

Затронутые файлы: app.py, src/duty_schedule/ui/config_io.py, src/duty_schedule/ui/views.py, src/duty_schedule/ui/components.py.
Общие модели: [data-model](../004-scheduling-validity/data-model.md).
Источники исследования: исходники и тесты, audit от 2026-10-10, read-only research
по domain/UI/API-CI. Модель календаря и норм общая; бизнес-проверка независима от
алгоритма и повторно используется для ревизий/экспорта. Раздельные нормы и часы
назначений исключают округление и расхождение экспортов.

Зависимости: 009-schedule-revisions.
Циклические ссылки означают контрактную интеграцию; реализация идёт в порядке
007 -> 008/004 -> 005/006 -> 009 -> 003/010 -> 011. История из 006 и контейнер
проекта из 009 проектируются совместно; доменная проверка не импортирует UI/API.

## Этапы

1. Написать регрессии требований и проверить текущий контрпример.
2. Реализовать модели/функции в указанной границе, затем адаптеры потребителей.
3. Проверить успешный, диагностический и несовместимый входы; провести ревью.
4. Дополнить evidence реальными командами; закрыть только проверенные задачи.

## Проверки и риски

- uv run pytest tests/unit/test_ui_workflow.py -q

Общие gates: check_sdd.py --base f432613, Ruff check/format src tests scripts,
mypy src scripts, pytest tests -q --ignore=tests/ui, покрытие и дополнительные
solver/security/UI/platform проверки. Внешние календарные данные в обычных тестах
заменяются полными fixture; недоступная проверка остаётся явным ограничением.


## Реализованное решение — 2026-10-11

app.py делегирует оркестрацию ui/components.py; типизированные YAML/table adapters проверяют вход до изменения state. UI хранит ScheduleProject и отображает одну текущую версию, sickness/norm/history/approval/R controls, pins/unpin, save/open и настоящий range. Каждый месяц повторного range берёт свой Config и свежий carry. What-if использует API patch schema, ловит CalendarError; diff показывает old/new R hours; legacy sorting/bulk/charts/cost/ICS остаются.

Runtime проверки и ограничения собраны в [общем evidence](../011-delivery-assurance/evidence.md); конкретные требования связаны с тестами в traceability.json. Подробный пользовательский переход — [руководство](../../docs/scheduling-workflow.md).

## Аудит012 — scope интеграции и продвижения

Сверка фактического cumulative diff к test/main дополнительно подтвердила
принадлежность следующих файлов этому контракту:

- `docs/scheduling-workflow.md`

Это уточнение области уже реализованных требований, не изменение смысла ID.
Результаты исходной реализации сохраняются; новый scoped gate и полный повторный
прогон отражены в evidence012.

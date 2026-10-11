# План: Проверки и проверяемая поставка

## Технический контекст и конституция

Python 3.12+, uv, Pydantic 2, существующий scheduler/FastAPI/Streamlit/export.
Работа напрямую в dev; чужие изменения сохраняются, feature.json не меняется.
SPECIFY_FEATURE_DIRECTORY указывает на этот каталог; SPECIFY_FEATURE_NO_PERSIST=1.
Новая функциональность имеет тесты; покрытие >=80%; без # комментариев в исходниках.

## Реализация и границы

Затронутые файлы: .github/workflows/, .github/actions/setup-python/action.yml, Dockerfile, tests/ui/, tests/e2e/, scripts/.
Общие модели: [data-model](../004-scheduling-validity/data-model.md).
Источники исследования: исходники и тесты, audit от 2026-10-10, read-only research
по domain/UI/API-CI. Модель календаря и норм общая; бизнес-проверка независима от
алгоритма и повторно используется для ревизий/экспорта. Раздельные нормы и часы
назначений исключают округление и расхождение экспортов.

Зависимости: 003-secure-api-exports, 004-scheduling-validity, 005-postprocess-integrity, 006-month-continuity, 007-calendar-shift-model, 008-workload-quality, 009-schedule-revisions, 010-ui-configuration.
Циклические ссылки означают контрактную интеграцию; реализация идёт в порядке
007 -> 008/004 -> 005/006 -> 009 -> 003/010 -> 011. История из 006 и контейнер
проекта из 009 проектируются совместно; доменная проверка не импортирует UI/API.

## Этапы

1. Написать регрессии требований и проверить текущий контрпример.
2. Реализовать модели/функции в указанной границе, затем адаптеры потребителей.
3. Проверить успешный, диагностический и несовместимый входы; провести ревью.
4. Дополнить evidence реальными командами; закрыть только проверенные задачи.

## Проверки и риски

- uv run pytest tests/unit/test_delivery_workflows.py -q

Общие gates: check_sdd.py --base f432613, Ruff check/format src tests scripts,
mypy src scripts, pytest tests -q --ignore=tests/ui, покрытие и дополнительные
solver/security/UI/platform проверки. Внешние календарные данные в обычных тестах
заменяются полными fixture; недоступная проверка остаётся явным ограничением.


## Реализованное решение — 2026-10-11

Setup использует frozen uv и explicit solver extra. Required solver workflow отвергает skips/empty JUnit. Бенчмарки проверяют ready и сравнивают реально восстановленный prior SHA baseline с mean:10%; promotion зависит от успешных gates. Main lint проверяет SDD linkage --base. Build проверяет installed wheel/native PDF, packaged-runtime выполняет API/UI без source mounts; tag/release — reusable dependencies того же SHA/version/manifest/checksum. Версия5.0.0 явно фиксирует несовместимый ready/export контракт старых входов без verified context.

Runtime проверки и ограничения собраны в [общем evidence](../011-delivery-assurance/evidence.md); конкретные требования связаны с тестами в traceability.json. Подробный пользовательский переход — [руководство](../../docs/scheduling-workflow.md).

## Аудит012 — scope интеграции и продвижения

Сверка фактического cumulative diff к test/main дополнительно подтвердила
принадлежность следующих файлов этому контракту:

- `docker-compose.yml`

Это уточнение области уже реализованных требований, не изменение смысла ID.
Результаты исходной реализации сохраняются; новый scoped gate и полный повторный
прогон отражены в evidence012.

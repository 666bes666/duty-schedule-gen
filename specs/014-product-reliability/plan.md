# План исправления сохранности и входных контрактов

Python 3.12+, uv, существующие domain/API/UI/export границы. Dev; feature.json
не записывать; SPECIFY_FEATURE_DIRECTORY выбрать явно, NO_PERSIST=1.

1. DATA-001/002: общая модель проверяет имя; редактор выбирает идентичность из
   команды вместо split имени. Persisted имена/ID и rename migration сохраняются.
   История сохраняет неизменённые полные CarryOverState; изменённые поля проверяют
   согласованность и происхождение. XLS сообщает ошибку, не возвращает урезанную
   успешно импортированную команду.
2. DATA-003/004: patch validator общий для UI/API; unknown nested paths/native422.
   Config проверяет matching calendar на модельной границе. Отдельный legacy YAML
   adapter сохраняет/сообщает известные unsupported-поля; без глобального удаления
   всех extra полей до проверки совместимости.
   UI смены периода сначала меняет calendar reference в исходных данных, затем
   валидирует новый Config. Текущее обратное выполнение этих шагов нельзя сохранить
   после усиления модели: оно ошибочно отвергало бы обычную смену месяца.
3. DATA-005: действующий core/quality пишет provenance в сериализуемом виде.
   Сравнение считает employee-day пары, сохраняет смены/часы и компоненты качества;
   UI различает unavailable log и no-op. Существующий pipeline не подменяет
   действующую цепочку.
4. Реальные failing regressions → ограниченные fixes → проверки → ревью → evidence.

Точные пути scope и planned selectors находятся в traceability.json; новые файлы
до реализации добавляются туда. Основные области: models, xls_import, project,
ui/builders/components/config_io/views, api/schemas/whatif_service/planning,
scheduler/core/postprocess/quality. Не изменять auth/rate limit/CI в этом контракте.

Проверки: product_integrity unit, product_inputs contract, product_recovery UI,
существующие history/XLS/what-if/error/export тесты; Ruff/mypy/SDD/index,
full pytest с coverage >=80%, UI. Native 422 имеет точные field locations;
сырой старый team_lead проверяется до типизированного удаления.

Риски: exact display-name сохранение и browser-widget representation могут
различаться; ID должен связывать их. Неполный старый XLS не становится полным
из-за догадок. Исправление не объявляется поставленным до этих новых проверок.

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

## Анализ перед реализацией 2026-10-11

Покрытие: DATA-001→T001/T006; DATA-002→T002/T006; DATA-003→T003/T007;
DATA-004→T004/T007; DATA-005→T005/T008. Противоречий с конституцией нет.
Дополнен scope input_validation.py и cli.py: общий strict input/patch validator
проверяет вложенные model fields; известный legacy team_lead мигрируется только
YAML адаптером с предупреждением, API нового входа отвергает extra. Редактор
использует list cells с выбором точных roster names; имена не парсятся по запятой.
Неизменённая history row возвращает исходный CarryOverState, изменённая требует
полные видимые counters. XLS сверяет roster metadata и сообщает номер строки.
Период calendar проверяется моделью до поиска; UI выбирает новый calendar до
model_validate. Оптимизация записывает сравнение employee-day состояний и часов,
подписанные quality components и source snapshots; ID добавляются при revision save.

Старый YAML contract test обновляется намеренно: unknown_fields_ignored заменён на rejected; example проверяется через legacy adapter. Путь добавлен до изменения.

E2E example fixture использует explicit legacy adapter; путь test_cli_workflow.py объявлен до изменения.

CP-SAT provenance сравнивает первую найденную допустимую раскладку с итогом мягких слоёв; до реализации область solver.py уже объявлена в 016/017, теперь привязана также к DATA-005. Реальные ID before не придумываются.

Перед поиском проверяются полные merged variants с точными native422 loc variants/index/patch. Старый integration partial-invalid-input scenario теперь ожидает 422 для всего запроса; его test path объявлен до изменения. Service-level runtime search failures остаются variant error.

Provenance после ручной правки не получает ID новой версии, если after snapshot
не совпадает с фактическими ячейками. Старый подтверждённый source ID сохраняется.
При load_project распознаваемые optimization/repair metadata проходят проверку
структуры до атомарной замены проекта; repair_candidate повторно валидируется.
Неверная новая metadata не должна приводить к сохранению проекта, который падает
при открытии UI. Дополнение входит в DATA-005 и действующий project.py scope.

## 2026-10-11 — завершение дополнительного независимого ревью

DATA-001: cleared editor None/NaN трактуются как пустой список без потери состава. DATA-003: external previous Schedule/DaySchedule/MonthlyTarget/Diagnostic отвергают unknown поля. API422 проверяется до поиска; OpenAPI snapshot обновлён для additionalProperties=false. Изменения покрыты уже согласованными точными files.

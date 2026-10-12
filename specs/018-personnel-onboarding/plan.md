# План шага 0 и независимой настройки работы

Дата: 2026-10-12. Статус: planned. Исходный dev: c561667.

## Проверенные границы

ui/components.py::_default_config и ui/state.py используют _DEFAULT_ROWS;
render_application немедленно вызывает new_project. Config.validate_team_constraints
при создании проверяет минимум дежурных. Employee требует schedule_type и имеет
on_duty=True по умолчанию. Нельзя использовать эти значения для незаданных ролей
или ослаблять Config ради UI. ScheduleProject format_version=1 требует config;
его нельзя создавать для неполного персонала.

## Решение

1. В отдельном ui/onboarding.py определить типизированный OnboardingDraft:
   ID черновика, период, персонал со случайными стабильными employee_id,
   name/city и nullable schedule_type/on_duty. Не менять публичные Config,
   Employee и ScheduleProject. Применение city lists валидируется атомарно;
   неизменённые строки при повторе/перестановке сохраняют ID. Для переименования
   после создания использовать ID существующего сотрудника.
2. render_application сначала предлагает восстановление/импорт и пустой шаг 0,
   затем шаг 1 черновика. Продолжение после ролей собирает существующий Config
   через явную проверку; при ошибке черновик сохраняется, поиск не вызывается.
   Новый полноценный проект создаётся только из валидного состава. Подготовка
   истории/календаря/норм продолжается прежним сценарием.
3. UI шага 1 поддерживает индивидуальные и групповые изменения; групповой action
   различает «не менять поле» и явное «Нет» участия. Итоги считают независимые
   множества по городам; ID скрыт от штатного редактирования. Подготовку нового
   проекта не смешивать с редактированием существующих revisions.
4. Расширить browser snapshot envelope и Python adapter распознаваемым draft
   payload; сохранить чтение существующих project snapshots. Общие locking,
   compare token, acknowledgement, valid backup и сообщение ошибки применяются
   также к draft. Неприменённая форма не объявляется сохранённой. При переходе
   draft→project не стирать последний корректный draft до успешной записи
   проекта; при ошибке доступен backup. Format черновика не меняет JSON проекта.
5. Импорт YAML/JSON и загрузка последнего проекта доступны до создания Config.
   Старые проекты не проходят принудительный onboarding и не получают marker,
   означающий неизвестные роли. Удаление/замена текущего состава остаётся в
   существующем update_config; проверить ID/history/pins и invalidation regression.
6. Убрать _DEFAULT_ROWS из runtime cold start, сохранив fixtures/examples;
   обновить тексты пути, browser fixtures по необходимости и индекс. Новые
   зависимости, изменения OpenAPI, CI или алгоритмов не требуются.

## Область изменения

Точные пути разрешённой реализации и документации перечислены в traceability.json.
Если необходим другой файл, сначала расширить files и анализ; не использовать
старый complete-контракт для разрешения посторонних изменений.

## Проверки

Сначала meaningful regressions для пустого старта, nullable ролей, атомарного
списка и поиска; затем targeted unit/browser, старые import/autosave journeys,
полный non-UI suite с coverage >=80%, полный UI suite, lint/format/mypy,
check_sdd scoped/staged и project_context --check. Проверить установленный wheel
для новых runtime modules, если меняется поставляемый код. Перед реализацией
прототипом проверить расширение autosave envelope с прежним snapshot.

## Риски и решения

Config не принимает неполный состав — отдельный draft предотвращает ослабление
business validation. Скрытые defaults создают ложную настройку — nullable поля
и явные selections. Перестановка списка не должна менять identity. Старый
browser snapshot нельзя перезаписывать пустым стартом до завершения restore.
Переход между draft/project и конфликт двух вкладок требуют отдельной приёмки.
API/CLI не получают новый nullable контракт.

## Уточнение исполнения 2026-10-12

Существующий browser bridge уже хранит JSON payload под token/hash/lock;
вместо нового JS protocol draft получает strict kind/version envelope в JSON
строке. Проект сохраняет прежний JSON. Переход draft→project использует тот же
ID storage key: последняя draft запись сохраняется как previous перед write,
expected token сохраняет защиту двух вкладок. Поле project в bridge — транспорт,
а не утверждение готовности payload. Старый read-first порядок сохраняется.
На стартовом экране поиск отсутствует; generate_project принимает только проект.
Проверка старого UI smoke на кнопку генерации меняется на ввод персонала
(точный путь tests/ui/test_schedule_generation.py включён до изменения).

Для независимой browser приёмки tests/ui/conftest.py запускает test-only wrapper:
календарный fetch для апреля2026 возвращает сохранённый fixture, без сетевого
запроса и без подмены генератора. Приложение не получает testing hooks. Новый
journey сохраняет полученный onboarding Config и вводит историю штатным XLS
импортом, затем реально рассчитывает/экспортирует без pins. Путь conftest
добавлен в scope до изменения. Индивидуальные роли представлены radio choices,
«не настроено» явно снимает назначение, group «не менять» сохраняет поле.
Переименование в черновике доступно по ID в индивидуальной форме шага1.

Полный non-UI прогон выявил 5 failures в старых AppTest harness: симулятор
не исполняет browser bridge и не отмечает завершение read-first storage phase.
Два существующих unit test files включены в scope до изменения harness; seeded
проекту явно устанавливается autosave_initialized=True в тесте. Проверяемые
period/revision/what-if сценарии не ослабляются и runtime restore guard сохраняется.

Полный browser прогон: 29/31 pass, два failures в harness. Quota-injection
отключала даже обновление last pointer для неизменного snapshot; теперь отказ
ограничивается записью project/backup, чтобы проверить именно transition write.
Старый project journey начинал вторую правку до окончания check rerun; в helper
добавляется ожидание конечного статуса и подтверждённого snapshot. Его точный
путь включён в scope до изменения, runtime изменения для этих failures не нужны.

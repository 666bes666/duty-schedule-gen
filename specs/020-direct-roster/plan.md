# План

Новый ui/roster.py: типизированная строка с nullable полями и отдельный RosterDraft,
табличное преобразование, delta edit и копирование ID. Draft допускает неполные/ошибочные
пользовательские значения; Employee/Config проверяются перед обновлением проекта.
RosterSnapshot version1 включает действующий project и сырые строки; загрузка project
через существующий строгий load_project. onboarding restore/storage сохраняют legacy
форматы, новый импорт — атомарный. Старые helpers сохраняются для compat unit tests.

Native data_editor вне form с on_change: cumulative delta применяется к стабильному
seed таблицы, новые строки получают стабильные ID, copy/delete/внешний импорт меняют
epoch. Это предотвращает повторное применение patch и потерю фокуса при autosave.
У существующего проекта валидные rows обновляют Config, invalid rows остаются поверх
его сохранённого основания. Иные tab edits сохраняют основание и draft атомарно.
Все расчёты/результат блокируются для invalid draft, публичная модель не ослабляется.

Один редактор/период для new/project. Автоматическая подготовка Config при полной
валидной команде; нет кнопки продолжения/сохранения состава. Файловая копия UI включает
draft при наличии незавершённых строк; plain JSON/YAML читаются прежним способом.
Legacy UI suite пересматривается под изменённое user-facing поведение с сохранением
проверок identity, recovery/conflict/quota, first-month, errors и imports. Исторические
spec018/019 получают явную отметку superseded UI, результаты evidence не удаляются.
Проверки: unit delta/ID/copy/migration/atomic import; AppTest Config сохранность; native
browser canvas editing + reload + meaningful error/first month. Ruff/mypy/coverage>=80%,
full UI, SDD/index/staged/committed gates, Python/code review, wheel.

Уточнение сохранения: для валидной применённой таблицы пишется прежний plain projectJSON,
из которого строки восстанавливаются без потерь. Roster envelope используется только
для неполного/ошибочного/ещё не применённого состава, сохраняя base. Это уменьшает
миграционный риск для существующих backup и browser consumers.

Browser выявил закрытие dropdown из-за полного rerun при autosave acknowledgement.
До исправления уточняем: render_autosave — fragment; saved ack обновляет только статус,
read/restore/retry/copy вызывают full rerun как раньше. New-project guard проверяется
при действии, чтобы fragment не оставлял кнопку навсегда disabled. Разрешены только
writes с ожидаемым token или последним token, который записал этот же iframe; foreign
writer token всё ещё вызывает conflict. Формат записи token/project/version не меняется.
Нужны browser sequential edits и two-tabs conflict; JS review обязательно.

Review обнаружил recovery-copy со старым seed.id: delta обязан сохранять current.id,
а copy recovery меняет epoch редактора. Unit и browser проверяют последующую правку
и reload отдельной копии; несовпадение draft/base ID недопустимо.

Full UI воспроизвёл stale callback предыдущего epoch после YAML import: старый период
менял новый draft/Config. Period/table callbacks игнорируют ключи не текущего epoch;
проверяются stale month/year и cumulative table delta, плюс существующий unpinned
YAML→first calculation browser сценарий. Черновик другого редактора не перезаписывается.

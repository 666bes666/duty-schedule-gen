# План подготовки и восстановления

Python 3.12+, uv; существующий ScheduleProject и Streamlit. Dev, явный feature
directory и NO_PERSIST=1. Domain/scheduler не импортирует browser API.

1. Общая preflight модель готовности использует те же правила входа/истории,
   что 014 и validator; UI преобразует диагностику в действие, без собственного
   альтернативного допуска ready. Проверки readiness и diagnostic search разделены.
2. Локальный browser storage adapter получает сериализованный ScheduleProject;
   запись версионированная/атомарная с последним корректным snapshot. Streamlit
   bridge сообщает успех/отказ и revision token, не хранит проект на сервере.
   Реальные пределы quota/origin проверяются прототипом до UI integration.
3. Восстановление только через load_project; открытие нового JSON атомарно заменяет
   current project и обновляет backup лишь после проверки. Unsubmitted forms
   помечаются отдельно от сохранённого состояния. Два writer одного project ID
   используют token/conflict detection, без молчаливого last-writer-wins.
4. Начальный экран ведёт по подготовке; технические поля остаются advanced.
   Сначала реальные recovery failure tests, затем integrated first-month journey.

Точный scope: traceability.json. Новые browser bridge файлы объявлены явно;
замена/новая зависимость требует обновить scope и обосновать совместимость.
CI/persisted API contract не меняются автоматически ради удобства UI.

Проверки: autosave adapter unit, actual browser restore/failure/conflict,
first_month_journey с полным saved calendar/history и незакреплёнными назначениями;
SDD/index/Ruff/mypy/full pytest+UI, >=80% package coverage.
Browser snapshot — удобство восстановления, скачиваемый JSON — перенос/резерв.
Если браузер запрещает storage, UI сообщает ограничение и сохраняет ручной JSON путь.

## Анализ перед реализацией 2026-10-11
FLOW-001→T001/T007; FLOW-002→T002/T004; FLOW-003→T003/T008;
FLOW-004→T005/T006. Покрытие полное, конституция соблюдена. Bridge реализуется
без новой зависимости через declare_component и штатный postMessage protocol.
localStorage принадлежит origin iframe; first read предшествует first write.
Каждая запись содержит format version, project ID, snapshot и compare token;
последний корректный snapshot хранится отдельно. Конфликт запрещает запись и
предлагает новый project ID/копию. Python принимает только соответствующее
hash acknowledgement; restore/load ошибки не меняют открытый project. Формы
отмечаются браузерным change event как неприменённые до следующего render.
Preflight использует validator пустого schedule с фильтрацией только входных
проблем; запускаемый поиск доступен отдельно как диагностическое исследование.

Browser write сериализуется Web Locks API по project ID: compare/read/write происходят под одним lock; unsupported locks сообщает failure вместо небезопасной записи.

Минимальный Streamlit поднимается до уже проверенной locked версии 1.65: keyed st.tabs и MultiselectColumn нужны для точных переходов и сохранных имён. Новая библиотека не добавляется; lock сохраняет проверенные версии. pyproject.toml/uv.lock объявлены в scope до изменения, чтобы wheel не обещал совместимость с неподдерживаемыми ранними API.

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

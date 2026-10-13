# Evidence

## 2026-10-13 — реализация и проверка

Основание: пользователь `approve` интервью и затем «приступай к реализации».
Исходный commit: 903cf74e9ae3e830f16d16a4463d826d382c6f7f, ветка dev.
Точные пути утверждены planned traceability до исходников. Прочитаны constitution,
SDD/cold-start, contracts018/019 и затронутые UI/tests. Анализ020 выполнен до реализации.

Среда: Python3.12, uv, UV_PROJECT_ENVIRONMENT=/tmp/duty-specs-20261011;
для PDF DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib. UI tests запускают собственный
offline Streamlit8503, browser origin отдельно от пользовательского8504.

- Новый direct draft позволяет пустые/частичные/ошибочные строки без ослабления Config.
  Применённый состав сохраняет plain projectJSON; ошибочный snapshot содержит draft+base.
- Copy переносит столбцы, очищает имя, создаёт ID; ID-based перенос сохраняет исходные
  отсутствия и не наследует их по имени для нового сотрудника.
- Saved ACK вынесен в fragment. JS допускает последний собственный физически записанный
  token; foreign writer продолжает вызывать conflict. JS reviewer APPROVE, syntax check
  и isolated rapid-own-write/foreign-token harness прошли.
- Python review выявил recovery-copy/old editor seed ID. До доставки исправлены current.id
  в delta и новый epoch при fork. Unit и browser conflict→copy→edit→reload прошли;
  повторный Python review APPROVE, direct-roster/autosave10passed.
- General code review APPROVE, без дополнительных замечаний; доставка обусловлена
  завершением полной регрессии. API/CLI/solver/public project serializer не изменены.

Промежуточные проверки:

- check_sdd.py --base HEAD: PASS для planned scope до реализации.
- Ruff: PASS; mypy: PASS, 71 source files.
- direct-roster/ui-workflow/product-integrity: 42passed после recovery исправления.
- Browser helper первоначально отправлял события до кадра canvas; надёжный helper
  синхронизирует hover через requestAnimationFrame, commit/dropdown через клавиатуру,
  сохранённые поля и отображаемый cell текст. Это изменение теста, не разрешение пропуска.
- Ошибочный import ожидает конкретную ошибку «Некорректный файл рабочего проекта».
  Corrupt primary сохраняется по прежнему протоколу: проверяются восстановленный DOM
  и скачанный previous snapshot, а не автоматическая перезапись повреждённой записи.

Полные regression, packaging и delivery результаты добавляются после завершения.


Полная регрессия выявила late callback прежнего period/table epoch после YAML import:
на следующем действии апрель менялся на ноябрь. До исправления это воспроизведено
в first-month browser test. Добавлены guards актуальных ключей до обращения к delta/
периоду; unit stale callback+current callback и browser первый расчёт прошли. Все
временные диагностические записи удалены из исходников. Повторные Python и general
code reviews APPROVE, direct-roster/autosave11passed.

Итог non-UI: `uv run pytest tests/ --ignore=tests/ui --cov=duty_schedule
--cov-report=term --cov-fail-under=80 -q`: exit0, 875 collected/passed,
88.28% branch-aware coverage (UI исключён существующей настройкой покрытия).
Полные Ruff check/format PASS; mypy PASS,71files. `uv build --wheel` PASS;
wheel содержит новый roster.py и autosave HTML. project_context --write/--check PASS,
check_sdd --base HEAD PASS. Native Cua8506: имя/Москва/5/2/Да→copy→reload,
копия с пустым именем и теми же настройками сохранилась; proof /tmp/duty-020-roster.jpg.
User preview8504 запущен с fileWatcherType none, сохранённые browser данные не менялись.

Последний полный UI прогон до корректировки helper:33passed, ошибочный helper ожидал
plain project при invalid roster envelope. wait_saved теперь проверяет revision base
project; standalone smooth suite4passed, включая375px иlight/dark. Form dirty indicator
проверяется на Seed в настоящей форме; год теперь является autosave полем. Заключительный
полный UI прогон выполняется без skip/xfail и его результат добавляется ниже.

## Заключительная проверка 2026-10-13

`uv run pytest tests/ui/ -q --tb=short --screenshot=only-on-failure
--output=/tmp/duty-020-ui-final`: exit0,36collected/passed, безskip/xfail.
После35pass/1flaky upload проверка в изоляции прошла; общий upload/download helper
ожидает завершения rerun и подтверждает имя ошибочного файла. Повторный общий36 UI
прогон прошёл, general review helper APPROVE. Error/snapshot assertions сохранены.

| Требование | Проверенное поведение |
|---|---|
| ROSTER-001 | Empty start, native cells, independent duty/5/2, valid first month/XLS |
| ROSTER-002 | Whole-row copy, hidden flags, fresh ID/blank name, no personal dates/history/pins |
| ROSTER-003 | Partial/invalid persistence, period/reload/backup, diagnostic/export block, conflict/quota |
| ROSTER-004 | Atomic old JSON/YAML/personnel import, recovery-copy ID, stale-epoch protection |
| ROSTER-005 | ID-based dates/references, same editor, calendar period, keyboard/375px/light+dark |

875 non-UI +36 UI passed. Coverage88.28% (existing non-UI configuration), Ruff/format,
mypy71files, SDD/index, packaging checks PASS. Python/JS/general reviews APPROVE.
Feature implementation and acceptance complete; T005 delivery remains open until push.


## Доставка dev 2026-10-13

Feature commit6523009: `feat(ui): start with an empty roster and copy employee rows`.
`check_sdd.py --staged`, Git cached diff check и pre-commit gates PASS;
`check_sdd.py --base HEAD~1` PASS. `git push origin dev` exit0,
remote dev903cf74→6523009 подтверждён. Все задачи и критерии020 закрыты.
Закрытие SDD статуса/index выполняется отдельным docs commit; full code regression
не повторяется для изменения только этих артефактов. PR67 dev→test обновляется
под итоговый direct-roster scope; дальнейшее продвижение требует CI соответствующегоSHA.

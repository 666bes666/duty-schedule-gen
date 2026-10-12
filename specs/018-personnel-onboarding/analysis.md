# Согласованность до реализации

2026-10-12. Содержательное ревью спецификации, плана и задач.

| Требование | Задачи | Свидетельство будущей приёмки |
|---|---|---|
| STAFF-001 | T004/T007/T008 | independent role choices + unchanged rules |
| STAFF-002 | T002/T003/T008 | empty start, parsing and atomic errors |
| STAFF-003 | T004/T008 | explicit partial/group choices and overlapping counts |
| STAFF-004 | T005/T008 | no search spy until configured and valid Config |
| STAFF-005 | T002/T006/T008 | IDs, partial draft round-trip, storage failures/conflicts |
| STAFF-006 | T003/T006/T007 | old imports, recover before empty write, no data loss |

Все три ответа владельца включены без взаимоисключающих требований. Незаданный
on_duty отличается от False; 5/2 отличается от участия. Проверки минимальной
команды не перенесены на ввод городского списка и не отменены на переходе в Config.
Неполный ввод не считается пригодным расписанием или полноценным Config.

Уточнения FLOW/UIC представлены отдельным дополнением 018 с сохранением ID,
старых completed tasks/evidence и существующего runtime. Для новой реализации
источником scope/приёмки служит 018. Точные paths включают индекс и новые тесты;
запланированные selectors ещё не существуют и не объявлены пройденными.

Выбор отдельного draft/envelope сохраняет публичный API и project JSON.
Технический прототип storage transition входит в T006; выявленный несовместимый
формат или необходимый новый путь требует обновления плана до реализации.

Результат: контракт согласован для реализации. Открытых продуктовых решений,
блокирующих описанный первый ввод, нет. Плановый статус не подтверждает выполнение
runtime criteria, удобство на реальной команде или новый passing test suite.

## Проверка реализации 2026-10-12

Typed draft отделён от Config. nullable поля сохраняются в explicit draft
envelope, independent role assignments и ID-based rename реализованы. Переход
использует тот же storage key; новый проект — новый key после hash-confirmed
записи. Old snapshots читаются прежним load_project. Общий JS storage protocol
не менялся; полноценные browser failures проверяют его с draft payload.
Для испытаний в scope добавлены legacy AppTest harness, UI conftest и project
journey, runtime границы не расширены. Independent Python review Approve.
Итоговые full suites и delivery фиксируются в evidence, не выводятся из gate.

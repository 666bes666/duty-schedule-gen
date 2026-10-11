# Комплексный аудит проекта — 2026-10-11

Исходный HEAD: f5ae141bffde227e7f005052832b87de8595dc37, dev, чистое дерево.
Итоговые команды, числа и доставка добавляются в [evidence](evidence.md).
[Полная карта файлов и контрактов](../../docs/project-index.md).

## Область и метод

Проверены все области репозитория: доменные модели и validator, calendar/history,
оба генератора и postprocess, ScheduleProject, API/auth/errors/what-if, CLI,
Streamlit, XLS/ICS/PDF, зависимости, Spec Kit, SDD документы, CI/build/release и
инструкции. Git inventory и AST индексируют все неигнорируемые файлы/определения;
тесты проверяют поведение, а независимые reviewer проверяют изменения и контракты.
Это инженерный аудит доступного кода и runtime, а не математическое доказательство
отсутствия всех дефектов и не правовая сертификация расчётов стоимости.

## Найденные проблемы и исправления

| ID | Проблема | Исправление и доказательство |
|---|---|---|
| A01 | SDD gate контролировал лишь src/app/api_main | Любой файл вне именованных SDD артефактов требует exact scope обновлённого planned-контракта; added/deleted/renamed и untracked проверяются |
| A02 | Посторонняя спецификация разрешала любой runtime diff | Каждый путь должен быть в `files`; негативные tests/unit/test_sdd |
| A03 | Pre-commit читал worktree вместо будущего коммита | `--staged` создаёт временный checkout-index snapshot; unstaged документы не прикрывают код |
| A04 | Обратное покрытие requirements и T-ID не проверялось | Bidirectional definitions↔mapping, уникальные задачи и per-ID evidence; мигрированы все контракты |
| A05 | Пустые, disabled, fixture и вложенные helper тесты могли служить evidence | AST проверяет настоящие test definitions, конструкторы/локальное наследование, __test__ и fixture; это структурный фильтр, фактическое выполнение доказывает pytest |
| A06 | Устаревшая архитектура v3 и архив комментариев | ARCHITECTURE переписана по v5; NOTES удалён; решения остаются в SDD |
| A07 | Старый построитель не использовался генератором | Удалены _build_day, три _select_* и dead _shift_limit_reached; шесть сценариев ограничений перенесены на build_candidate |
| A08 | Dashboard принимал неиспользуемый employees_df | Параметр и единственный вызов упрощены; UI journey пройден |
| A09 | Не было полного индекса и воспроизводимого входа | project_context.py создаёт JSON/Markdown, индексирует вложенные/условные определения, imports, 78требований и13API операций; cold-start.md |
| A10 | Ignored metadata/schema попадали в первоначальный индекс | Все данные index получаются только из Git inventory; ignored и внешние symlinks отвергаются/исключаются, filenames сохраняются побайтно по NUL разделителю |
| A11 | SDD не требовался branch protections, main check names устарели | Live required checks исправлены на всех трёх ветках, app_id15368; review/force/deletion/admin настройки сохранены в github-protection.json |
| A12 | Release graph мог обойти standalone index gate | Main lint включает index check; dev/test lint тоже проверяют scoped SDD+index, чтобы продвижение benchmark зависело от gate |
| A13 | Правила процесса не запрещали обход для всех видов работы | Конституция1.1.0, AGENTS/CLAUDE/CONTRIBUTING, templates и docs прямо запрещают вне-SDD изменения, включая hotfix/refactor/docs/test/CI |

Все контрпримеры gate/index воспроизводились до исправления. Исторические evidence
сохранены; общие сценарии v5 заменены конкретными, ID не менялись. SDD-003/004/006
из001 расширены явно, контракт возвращён в рабочий статус до новой приёмки.

## Что сохранено и почему

- Baseline и прежние evidence сохраняют историю исходного состояния. Это не
  активная legacy реализация и не текущая гарантия: новые факты/источники добавлены
  отдельными датированными разделами.
- `CarryOver.source=legacy` и unverified календарь явно диагностируют старые
  входы. Удаление маркеров уничтожило бы объяснение отказа ready для неизвестных данных.
- Pipeline/stages/helpers имеют вызываемые интерфейсы и живые POST/HOURS контракты,
  атомарные guardrails и integration tests. Они сохранены как проверяемый интерфейс
  постобработки; действующая генерация ready использует quality.optimize_candidate.
- Spec Kit1.1.3 scripts/integration manifests/upstream license сохраняют provenance
  и локальные адаптации. Template placeholders — образцы, не незавершённые требования.

## Текущие ограничения

AST и структурный gate не проверяют смысл assertion и истинность заявленного PASS.
Динамическая генерация тестов/наследование из стороннего модуля не принимаются как
статически подтверждённый selector; новый случай требует явного расширения контракта.
UI исключён из числового coverage приложения прежней конфигурацией, но его actual
journeys проверяются pytest/Playwright отдельно. Excel2016 не запускался; openpyxl
не доказывает Excel runtime. PDF smoke не заменяет оценку печати любых команд.
Rate limiting — process-local; публичные docs не отключают auth бизнес-endpoints.

Direct-dev flow сохранён. GitHub admin enforcement существующей политики выключен;
администратор технически может override. Direct dev push этого аудита получил
штатное admin allowance для ещё ожидаемых remote checks; локальные gates перед
push выполнены. Административный merge не выполнялся. Для test/main нужен review.
CI старого SHA не является evidence нового. Пользователь уточнил поставку только
в dev: test/main отложены. Complete012 требует dev CI и evidence опубликованного
коммита; будущее продвижение остаётся отдельным поручением.

## Приёмка согласованной поставки в dev

78требований/13каталогов, все задачи аудита закрыты. Runtime794tests, UI7,
packaged2, cold70, application coverage87.64%, tooling91.25%; независимые reviewers
APPROVE. Sourcea069b94: Dev/SDD/Test CI success,4platform jobs исполнены.
Подробные даты/команды/ограничения: evidence.md. В main/test код не продвигался
по уточнению пользователя; прежняя review policy остаётся для будущего поручения.

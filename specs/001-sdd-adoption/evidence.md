# Результаты перехода на SDD

Дата: 2026-10-10 (Europe/Moscow). Исходный HEAD:
`949b6bc53ba649d496d130545acb81a8dc6f656d`. Изменение касается процесса и
проверок разработки; runtime-исходники приложения не изменены.

## Приёмка требований

| ID | Проверка | Фактический результат |
|---|---|---|
| SDD-001 | Init в временной директории; integration status; helper smoke | Spec Kit 1.1.3, Codex + Claude, missing managed files 0, invalid paths 0; ветка осталась dev |
| SDD-002 | Baseline audit; AST/validator сверка test selectors | 27 требований, 168 связей с существующими тестами, отдельные gaps; ссылки корректны |
| SDD-003 | Позитивные/негативные тесты валидатора | Стадии, документы, некорректные JSON/ID/пути/selectors, задачи и evidence проверены |
| SDD-004 | Disposable git repos: обычный diff, rename, удаление evidence | Изменение runtime без surviving feature-артефакта отклоняется; baseline/draft не заменяют planned feature |
| SDD-005 | Контрактный snapshot test; добавление route в изолированном probe; повторная генерация с другим env | Parity проходит, новая операция вызывает drift, результат не зависит от env-настроек auth |
| SDD-006 | Независимое governance review, Markdown links, workflow info | Руководства и шаблоны согласованы, ссылки корректны, workflow распознаёт шесть этапов |

## Выполненные команды

```bash
uv run python scripts/check_sdd.py
uv run python scripts/check_sdd.py --base 949b6bc53ba649d496d130545acb81a8dc6f656d
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run mypy src/ scripts/
uv run pytest tests/unit/test_sdd.py tests/contract/test_openapi_snapshot.py -q
uv run pytest tests/ --ignore=tests/ui -o addopts='' -q -ra --cov=duty_schedule --cov-report=term --cov-fail-under=80
uv run python scripts/export_openapi.py
uvx --from specify-cli==1.1.3 specify integration status
uvx --from specify-cli==1.1.3 specify workflow info speckit
git diff --check
```

- Ruff и форматирование: успешно (135 Python-файлов).
- Mypy: успешно, 52 файла; остались информационные заметки об unused sections
  для optional-модулей, ошибок нет.
- Целевые SDD/OpenAPI тесты: **27 прошли**.
- Полная локальная проверка без UI: **610 прошли, 7 пропущены**, 25,53 с.
- Покрытие пакета `duty_schedule`: **86,18%**, установленный порог 80% пройден.
- Integration status: WARNING только о пяти намеренно изменённых managed-файлах
  (2 skill adapters, 3 templates); missing files/invalid paths — 0. Локальные
  изменения и политика обновления описаны в `.specify/UPSTREAM.md`.
- Workflow info распознал specify → plan → tasks → analyze → implement → converge
  без дополнительных человеческих approval gates.

Helper smoke выполнялся в disposable git-репозитории с `git init -b dev` и
`SPECIFY_FEATURE_NO_PERSIST=1`: create-new-feature → setup-plan → setup-tasks →
запись полученного tasks template → check-prerequisites
`--require-spec --require-tasks --include-tasks`. Все helpers завершились успешно,
plan/tasks существуют, текущая ветка `dev`, локальный pointer не появился.
`setup-tasks` возвращает шаблон для агента, сам файл задач не записывает.

## Независимое ревью и исправления

- `python-reviewer`: APPROVE после исправления трёх найденных дефектов:
  source rename учитывается как delete+add; управляющие символы в test paths
  отклоняются без traceback; удалённый optional evidence не считается
  сопровождением изменения. Для каждого дефекта проверен failing-before /
  passing-after регрессионный сценарий. Независимо повторены 27 тестов,
  Ruff, форматирование и mypy.
- `code-reviewer`: APPROVE, блокирующих замечаний нет. Устранены несогласованность
  документации о будущих тестах и дополнительные approval gates в bundled workflow.
- Первоначальные две ошибки mypy исправлены явной проверкой строковых типов
  kind/status; конечные результаты выше относятся к исправленной реализации.

## Пропуски и пределы доказательств

- Один benchmark-модуль пропущен: `pytest_benchmark` не установлен.
- Три PDF-теста пропущены: системные библиотеки WeasyPrint недоступны.
- Три CP-SAT теста пропущены: `ortools` не установлен.
- `tests/ui` исключены из локального запуска. Их штатные CI-проверки сохранены.
- Локальное покрытие относится к пакету приложения; валидатор проверяется
  subprocess-сценариями, его отдельный coverage процент не измерялся.
- OpenAPI snapshot фиксирует текущую схему, включая существующие пробелы,
  описанные в `specs/000-baseline/gaps.md`. Он не доказывает весь HTTP-контракт.
- Структурный gate не устанавливает смысловую достаточность тестов и правдивость
  evidence. Их проверяют ревью и тесты поведения.
- Проверки API/schema и helpers не обращались к производственным ресурсам.

## Доставка

Изменение подготовлено для прямого commit/push в `dev`. Результаты удалённого
GitHub CI проверяются после push отдельно; локальная приёмка выше не означает
заранее успешный удалённый запуск. Продвижение в `test`/`main` и релиз не выполнялись.

### Проверка GitHub после push

Проверен commit `ecfc81b6c622b835c9081fee500f53d5f5b69c77` в `origin/dev`:

- [SDD Gate](https://github.com/666bes666/duty-schedule-gen/actions/runs/37994368871):
  **success**. Структура/diff, Ruff, mypy и целевые тесты прошли в Linux CI.
- [CI Dev](https://github.com/666bes666/duty-schedule-gen/actions/runs/37994368818):
  **failure** только в Dependency Audit. Unit Tests, Lint и Smoke Tests — success.
- `pip-audit` сообщил 78 известных уязвимостей в 10 пакетах установленного
  окружения. Требуется отдельное обновление зависимостей и проверка совместимости.
  `pyproject.toml` и `uv.lock` в переходе на SDD не изменены; старый lock-file
  сохранён. Уязвимости не подавлялись, security gate не отключался.
- Состояние SDD-миграции принято по её требованиям и локальным/SDD CI-проверкам.
  Общий CI не зелёный, поэтому автоматическое продвижение в `test`/`main`
  не выполняется. Draft PR используется для ревью готового изменения.


### Последующее устранение blocker: обновление зависимостей

2026-10-10: отдельное изменение [002-dependency-update](../002-dependency-update/evidence.md)
обновило зависимости. Ранее зафиксированный audit failure остаётся историческим
результатом. На commit `6faea7a` dev/PR security и остальные проверки прошли;
первоначальный blocker больше не действует для этого проверенного изменения.

## 2026-10-11 — миграция к строгому SDD и явная приёмка

Область `files` восстановлена из плана и реальных файлов. Это актуализация
живого контракта, а не утверждение о ретроспективном прохождении нового gate.

| ID | Проверяющие тесты | Evidence |
|---|---|---|
| SDD-001 | `tests/unit/test_sdd.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SDD-002 | `tests/unit/test_sdd.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SDD-003 | `tests/unit/test_sdd.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SDD-004 | `tests/unit/test_sdd.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SDD-005 | `tests/contract/test_openapi_snapshot.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| SDD-006 | `tests/unit/test_sdd.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |

## 2026-10-11 — новая приёмка SDD-003/004/006 завершена

T008–T010 закрыты: новый scoped/staged/AST gate проверен negative regressions,
полный итог794tests/87.64% и tooling91.25%; isolated cold clone70tests и hooks pass.
SDD-003: bidirectional IDs, T-ID, test nodes, per-ID evidence; SDD-004: exact file
scope, worktree/untracked/staged, origin/test/main integration; SDD-006: строгие
общие инструкции, индекс и холодный старт. Независимые Python/code reviewers
APPROVE без открытых серьёзных замечаний. Реальные команды и ограничения:
[evidence012](../012-project-audit/evidence.md). Контракт001 снова complete;
продвижение audit012 через GitHub — отдельная незавершённая задача T008 того изменения.

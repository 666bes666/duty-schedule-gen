# Evidence продуктового аудита

## 2026-10-11 — исходное состояние и read-only аудит

Исходный SHA: f6fe168fbbc189a4d67a499de19c1be14bcd1e41, branch dev,
version 5.0.0; первоначальное дерево чистое. Изучены AGENTS/CLAUDE, конституция,
SDD, cold-start, CONTRIBUTING, index, product workflow, текущие контракты 003–012,
исходники и тесты. Предыдущие результаты аудита 012 не подменяли live проверки.

Применены проектные speckit-analyze/clarify и Postman api-engineer; API проверен
существующими контрактами и локальным TestClient. Postman cloud/workspace
не создавался и данные туда не отправлялись. Для визуального UI использован
playwright skill и отдельная browser session duty-product-audit.

Runtime: новое `/tmp/duty-product-audit-20261011-01a12acc`, Python 3.12.12.
`UV_PROJECT_ENVIRONMENT` задавался явно; все исполнения после sync использовали
`uv run --no-sync`. PDF получил существующие native libraries через
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`. Dependencies/lock не менялись.
SPECIFY_FEATURE_NO_PERSIST=1; feature.json не записывался.

| Команда / проверка | Фактический результат |
|---|---|
| `uv sync --locked --all-groups --extra solver` с новым UV_PROJECT_ENVIRONMENT | exit 0, установлен новый locked runtime |
| `uv run --no-sync pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-report=json:/tmp/duty-product-audit-coverage.json --cov-fail-under=80 --junitxml=/tmp/duty-product-audit-tests.xml --tb=short` | exit 0; 794 tests, 0 failures/errors/skips; 275,110 s; coverage 87,62975778546713%, branch coverage 80,9375% |
| `DUTY_TEST_STREAMLIT_URL=http://127.0.0.1:18511 uv run --no-sync pytest tests/ui -q --junitxml=/tmp/duty-product-audit-ui.xml --tb=short` | exit 0; 7 tests, 0 failures/errors/skips; 27,447 s |
| `uv run --no-sync duty-schedule validate config.example.yaml` | exit 0; корректный Config, 11 сотрудников, дежурных Москва 5 / Хабаровск 3 |
| `uv run --no-sync duty-schedule version` | exit 0; 5.0.0 |
| `check-prerequisites.sh --json --require-spec --require-tasks --include-tasks` с feature 013 и NO_PERSIST=1 | exit 0; выбран правильный каталог, tasks доступны |
| `uv run --no-sync python scripts/check_sdd.py --base HEAD` после spec/plan/tasks/traceability | exit 0; SDD checks passed |

Full pytest содержит предупреждения upstream Starlette/httpx и Python deprecation;
они не объявляются дефектами продукта без воспроизведения. Application coverage
настроен без UI; этот процент не доказывает покрытие всего пользовательского пути.

## Дополнительные экспериментальные проверки

Источник первых probes: `/tmp/duty-product-audit-probes.py`; запуск:
`PYTHONPATH="$PWD" UV_PROJECT_ENVIRONMENT=/tmp/duty-product-audit-20261011-01a12acc
uv run --no-sync python /tmp/duty-product-audit-probes.py`.
Результат `/tmp/duty-product-audit-probes.json`, лог `/tmp/duty-product-audit-probes.log`.
Первый запуск без PYTHONPATH не нашёл `tests.conftest`; повторный корректный запуск
завершился exit 0. Это настройка исследовательского скрипта, не сбой приложения.

Эксперименты используют готовый `journey_config/journey_days` с синтетическим
календарём и pins для проверки границ. Проверка приоритетов/предпочтений использует
незакреплённый `complete_config` с weekday calendar, а не реальный нормативный
календарь владельца. Результаты и минимальные шаги сохранены также в audit.md,
поэтому /tmp не является единственным источником вывода.

| Сценарий | Факт |
|---|---|
| PLOG-01, blank employee | ready; 6 employees; XLS импорт 0 histories |
| PLOG-01, имя с запятой | `Иванов, Иван`: ready до неизменённого editor round-trip, diagnostic после |
| PLOG-02 | Сохранение неизменённой UI history: consecutive_off 4 → 1 |
| PLOG-03 | solverr patch полностью игнорируется; API HTTP 200 / variant success; UI запрещает ключ |
| PLOG-04 | config validate HTTP 200 valid=true; тот же mismatched calendar в plan даёт HTTP 502 calendar_error |
| PLOG-05 | standard optimizer seed 0 меняет assignments и quality 77 → 52 по первому компоненту; changelog отсутствует |
| PLOG-06 | 4 priorities: все ready, 1 уникальный результат; CP-SAT morning/evening preferences: оба ready, одинаковые assignments |
| PLOG-07 | ready; carry streak 2 + первые 3 рабочих дня = 5; compute_stats max_streak_work=3 |
| PLOG-08 | 3 checks без правки: 1 → 4 revisions |
| Отвергнутая гипотеза | is_holiday=true на рабочую 01.04 нормализуется false, XLS helper=0; противоречие экспорта не подтвердилось |

Дополнительные результаты: `/tmp/duty-product-audit-inputs.json`,
`/tmp/duty-product-audit-identity.json`. Вход timezone Wrong/Zone принимается;
неизвестное solvver отбрасывается; team_lead из example не сохраняется в typed YAML.
Это требует анализа legacy совместимости, а не автоматического удаления поля.

## Визуальная проверка

Локальный Streamlit запущен на 127.0.0.1:18511 с headless=true и usageStats=false;
серверный лог `/tmp/duty-product-audit-ui-server.log`. Playwright CLI запускался
через bash, поскольку wrapper не имеет executable bit; права wrapper не менялись.

Первый экран: Seed, greedy/cpsat, editable Europe/Moscow и широкая таблица.
Скриншот `/tmp/duty-product-audit-browser/first-run.png`. Snapshot и последующие
наблюдения в `.playwright-cli/` этого временного каталога.
Первый расчёт дал диагностическую версию за неизвестную исходную историю;
после reload заголовок текущей версии исчез, остался новый пустой проект.
Этот UI расчёт обращался к источнику календаря; точность полученного календаря
не является отдельным доказанным выводом аудита. Все API probes были без сети.

## Приёмка требований на текущем этапе

- PAUD-001: основные области проверены; покрытие и ограничения в матрице audit.md.
- PAUD-002: пять дефектов воспроизведены; четыре пробела/ограничения выделены отдельно.
- PAUD-003: интервью ещё не завершено; ответы не выдуманы.
- PAUD-004: будущие контракты ожидают интервью; runtime исправления не выполнялись.
- PAUD-005: runtime/UI/initial SDD пройдены; итоговый index и SDD отмечаются отдельной записью после отчёта.

Complete не установлен. T004–T006 остаются открытыми до ответов владельца,
уточнения спецификаций и итогового анализа. Исторические evidence не переписаны.

## 2026-10-11 — сохранённый отчёт и согласованность SDD

После отчёта выполнены `project_context.py --write`, `project_context.py --check`,
`check_sdd.py --base HEAD` и `git diff --check`: все exit 0. Generated index
включает новую 013 спецификацию, пять требований и текущее состояние задач.
Ruff check src/tests/scripts/app.py/api_main.py: pass; Ruff format --check:
168 files already formatted; mypy src/scripts: success, 66 source files.
Изменены только SDD-артефакты и generated index, исходники/тесты/lock не менялись.

Read-only speckit-analyze текущего аудита: 5 требований, 7 задач;
100% требований имеют задачи, несопоставленных задач/дубликатов ID нет.

| Требование | Задачи | Проверенный статус |
|---|---|---|
| PAUD-001 | T001 | матрица областей и источники есть |
| PAUD-002 | T002 | воспроизведения и отделение гипотез есть |
| PAUD-003 | T004 | один вопрос задан, ноль ответов; остаётся открытым |
| PAUD-004 | T005/T006 | контракты дальнейшей разработки ожидают интервью |
| PAUD-005 | T003/T007 | runtime/UI/gates pass; итоговая поставка ещё открыта |

Конституционных конфликтов и непокрытых файлов в текущем этапе не обнаружено.
Материальная неопределённость будущих контрактов: где выполняются основные правки
и как защищается незаписанная работа. Это не препятствует завершённому read-only
аудиту, но не разрешает зависящую от ответов реализацию. Итоговый analyze T006
будет проверять новые продуктовые контракты после интервью; этот предварительный
анализ его не подменяет.

Локальный сервер 18511 и временная браузерная сессия после проверки остановлены.
Созданная инструментом Serena временная конфигурация удалена; project rules не
менялись. Коммит/push в этом промежуточном этапе не выполнены. Не заявляется
доставка в GitHub или завершение всего поручения.

## 2026-10-11 — интервью, ответ 1

Владелец прямо выбрал: «В приложении; Excel/PDF — для выдачи (рекомендую)».
Ответ внесён в Clarifications и US2. Основной путь будущих контрактов — правки
в UI и единая текущая версия проекта; полный обратный импорт правок Excel не
добавляется по предположению аудитора. Существующий импорт прошлой истории
сохраняется. Принят 1 ответ; T004/T005/T006 ещё открыты.

## 2026-10-11 — интервью, ответ 2

Владелец прямо выбрал: «Автосохранение и восстановление в том же браузере
(рекомендую)». Ответ внесён в Clarifications и US2. Восстановление рабочего
проекта и резервный JSON будут описаны проверяемыми требованиями; серверное
хранение/синхронизация устройств не предполагаются. Принято 2 ответа.

## 2026-10-11 — интервью, ответ 3

Владелец выбрал: «Менять как можно меньше остальных назначений (рекомендую)».
Ответ внесён в Clarifications и US2. Минимизация изменений относится к повторному
расчёту существующей версии, а не к первому построению без baseline. Pins и
безусловные правила сохраняются; глобальный минимум не обещается без доказанной
оптимальности поиска. Принято 3 ответа.

## 2026-10-11 — интервью, ответ 4

Владелец выбрал: «Текущий и предыдущий месяц», отклонив рекомендованное окно
трёх месяцев. Применено окно ровно двух месяцев с пропорциональной выбранной
нормой и подходящими пулами каждого периода. Недостающая история качества
отображается явно и не подменяет обязательный carry-over отдыха. Принято 4 ответа.

## 2026-10-11 — интервью, ответ 5 и завершение

Владелец выбрал: «Подготовка данных и первый расчёт (рекомендую)» как первый
пользовательский путь после исправления ошибок. Ответ применён к US2; T004 закрыт.
Задано пять вопросов, принято пять ответов. Новых человеческих согласований для
документирования этих решений не требуется. T005/T006/T007 ещё выполняются.

## 2026-10-11 — обновлённые контракты и финальный анализ

PAUD-003 принят: 5 вопросов/5 прямых ответов; по одному, каждый ответ сразу
применялся к US2/Clarifications. Прежние hard rules/норма/approvals сохранены.
PAUD-004 принят на уровне спецификаций: созданы 014–017 с 14 требованиями,
29 открытыми задачами и точными будущими source/test scopes; пять живых 003/006/
008/009/010 возвращены в planned, старые ID/evidence сохранены, добавлены четыре
новых ID. Runtime и tests не реализовывались. Решения записаны в decisions004;
baseline gaps содержит только текущие воспроизведённые факты.

Read-only speckit-analyze всех новых контрактов: prerequisite paths проверены
для каждого с NO_PERSIST=1, spec/plan/tasks/traceability сопоставлены.

| Контракт | Требований | Задач | Требования с задачами | Итог |
|---|---:|---:|---:|---|
| 013 аудит | 5 | 7 | 100% | осталось завершить доставку документов |
| 014 данные | 5 | 8 | 100% | planned, реализация не начата |
| 015 подготовка/backup | 4 | 8 | 100% | planned, первый UX этап владельца |
| 016 repair | 2 | 6 | 100% | planned, hard rules/norm/pins выше числа правок |
| 017 качество | 3 | 7 | 100% | planned, ровно два месяца |

Исправлены смысловые неопределённости до приёмки документов:
1. Provenance оптимизации не требует вымышленных revision ID до сохранения
   результата — связывает состояния, затем реальные ID.
2. Внешняя quality history не считается verified по неотрицательным агрегатам:
   нужен полный предыдущий Schedule, общий validator и пересчёт источников.
3. Двухмесячный calculator имеет конкретную арифметику и independent rational
   контроль: 34/26 даёт4/7, 35/25 даёт10/7; Fraction-проверка подтверждает значения.
4. Первый расчёт не имеет слоя минимизации изменений; repair имеет, а
   month-only отсутствие прошлой quality history обозначается явно.

Открытых конституционных/критических смысловых противоречий в выбранном объёме
не обнаружено. Вопросов владельцу не осталось. Browser bridge/quota проверяется
прототипом будущей T002015; клиентская active revision внешнего snapshot не
считается доказанной без проекта. Это границы реализации, а не пропущенные ответы.

PAUD-001/002 остаются принятыми audit/probes; PAUD-005: scoped SDD/index/diff pass.
Новые planned selectors ещё отсутствуют, это явно обозначено в каждом evidence.
Индекс содержит18спецификаций; его окончательные статусы регенерируются перед
staged snapshot. T005/T006 закрыты; T007 выполняется до опубликованного dev SHA.

## 2026-10-11 — опубликованный контрактный коммит

Коммит `087be98e8a3289ff55becf4e654b4979f737a7d2`
(`docs: audit product logic and specify authoring improvements`) опубликован в
origin/dev сразу после staged gates/commit. Изменены55точных путей документов;
src/tests/scripts/config/lock/runtime не менялись. После push дерево было чистым.
Снимок нового индекса:18спецификаций,101требование.

Перед commit: `check_sdd --staged`, `check_sdd --base HEAD`, index --check и
diff --check pass; hooks SDD/format/Conventional Commit pass. Перед push:
`check_sdd --base HEAD~1` и index --check pass. Ruff/format/mypy текущих
неизменённых исходников прошли; дополнительный прогон изменённого SDD/index
контекста70passed/0failures/0errors/0skips,4,677s
(`/tmp/duty-product-contract-checks.xml`). Full794/UI7 результаты относятся
к тем же неизменённым исходникам; не утверждается, что новые planned tests запускались.

Обычный dev push получил серверное сообщение `Bypassed rule violations:
5 of 5 required status checks are expected`. Это существующий admin allowance
прямого dev flow; защиты/review policy не менялись и merge не выполнялся.
Remote CI выполняется после push, локальные gates выполнены до него.

На этом SHA оба SDD Gate уже success:
[push](https://github.com/666bes666/duty-schedule-gen/actions/runs/38142385643),
[existing PR](https://github.com/666bes666/duty-schedule-gen/actions/runs/38142388313).
CI Dev/Test ещё проверяются; их завершение фиксируется следующей записью.

## 2026-10-11 — подтверждённая приёмка в dev

Тот же опубликованный SHA087be98e8a3289ff55becf4e654b4979f737a7d2 получил success:
[CI Dev](https://github.com/666bes666/duty-schedule-gen/actions/runs/38142385637),
[CI Test](https://github.com/666bes666/duty-schedule-gen/actions/runs/38142388311),
оба SDD Gate из предыдущей записи. CI Test выполнил Ubuntu/Windows Python3.12/3.13,
security, performance, required CP-SAT без skips и Streamlit smoke. Продвижение
в test/main и merge существующего PR не выполнялись.

PAUD-001: матрица всех продуктовых областей, проверенные источники и ограничения.
PAUD-002: пять воспроизводимых дефектов, отдельные gaps/ограничения и отрицательный
контроль календарного флага; минимальные шаги/последствия сохранены в audit.md.
PAUD-003: пять принятых ответов применены, неполученных согласований нет.
PAUD-004:14future requirements/29tasks, обновлённые пять живых контрактов и
финальный анализ без открытых критических противоречий; ID и префиксы исторического
evidence пяти контрактов дополнительно проверены программно и сохранены точно.
PAUD-005: full794/UI7, дополнительный SDD/index/OpenAPI70, local/staged gates,
dev push и verified CI опубликованного SHA. Все задачи аудита закрыты.

Complete относится к аудиту, интервью и обновлению спецификаций, не к реализации
014–017. Будущие контракты и пять переоткрытых features остаются planned с
открытыми задачами. Заключительное bookkeeping evidence/status/index публикуется
отдельным docs-коммитом; code/test/lock от проверенного SHA не меняются.

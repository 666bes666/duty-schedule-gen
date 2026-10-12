# Evidence 018

## 2026-10-12 — интервью и контракт

Владелец выбрал три варианта А: независимые график/дежурства; два списка имён
по городам с автоматическим количеством; незаданные роли с индивидуальным/
групповым назначением и блокировкой расчёта до настройки всех.

Прочитаны AGENTS, конституция, docs/sdd.md, CONTRIBUTING, CI SDD workflow,
контракты 010/015 и исходники ui/components.py/state.py/mappings.py,
models.py/project.py. Проверены существующие first-month browser fixtures.
_default_config использует _DEFAULT_ROWS; Config проверяет минимум команды,
ScheduleProject требует Config. Эти факты обосновывают отдельный draft.

STAFF-001–006 пока не реализованы, запланированные тесты не созданы и не
запускались. T001 закрывается только для исследования/интервью/документов.
Результат содержательного анализа: analysis.md. Runtime, API/CLI, текущая
локальная test-сессия и старые evidence не изменяются.

## Проверки документов

Первый `uv run python scripts/check_sdd.py --base HEAD` отверг analysis.md:
этот дополнительный файл не входит в стандартный набор SDD-артефактов и требует
точного scope. Путь добавлен в files текущего planned-контракта до реализации.
`uv run python scripts/project_context.py --write` и `--check` прошли.
Повтор scoped gate и повторная проверка индекса фиксируются ниже по результату.

Итог: повторный `uv run python scripts/check_sdd.py --base HEAD`: PASS;
`uv run python scripts/project_context.py --check`: PASS;
`git diff --check`: PASS. После записи этого результата индекс регенерирован
и проверен повторно; runtime tests не запускались для изменения только документов.

## 2026-10-12 — реализация и проверка

Реализация поручена владельцем после интервью. Runtime основан на dev c561667.
Файлы scoped до изменения; исходники/зависимости API/CLI и алгоритмы не изменены.
Для команд runtime использовано UV_PROJECT_ENVIRONMENT=/tmp/duty-specs-20261011;
для native PDF DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib.

TDD: новый unit module до реализации завершился ModuleNotFoundError для
ui.onboarding; после реализации targeted suites прошли. Последний расширенный
прогон onboarding/autosave/ui_workflow/product_integrity: 51 passed, 9.07s.
Первый полный non-UI прогон выявил 5 AppTest harness failures: симулятор не
исполняет JS storage bridge. Scoped harness явно отмечает initialized у
предварительно загруженных проектов; поведение старых сценариев сохранено.
Полный стабильный повтор выполняется; результат добавляется ниже.

Browser проверки сначала выявили неправильное автоматизированное открытие
selectboxes и гонку после form submit. Для небольшого выбора ролей UI использует
radio; helper ждёт reset нового form epoch. Дополнены meaningful tests
ID-based переименования, сброса ролей и отдельного нового проекта.
Независимый путь без Config substitution: чистый ввод имён/ролей, календарь
через штатную кнопку (test-only saved fetch), исходная история через XLS,
реальный default greedy без pins, XLS download и reload: 1 passed, 9.26s.

Первый полный browser suite: 29 passed / 2 failures в harness. Quota injection
запрещала даже idempotent last pointer update после restore; теперь запрещает
project/backup запись, чтобы проверять transition. Старый revision journey
ждал следующую правку раньше окончания check rerun; helper теперь ждёт итоговый
status и подтверждение snapshot. Полный стабильный повтор выполняется.

- Ruff check src/tests/scripts: PASS; format 184 files: PASS.
- Mypy src/scripts: PASS, 70 source files.
- Scoped SDD gate (--base HEAD), project_context --check, git diff --check: PASS.
- uv build --wheel: PASS. uv pip install --target /tmp/duty-onboarding-wheel-20261012
  --no-deps: PASS. Fresh python -I с wheel path первым импортировал именно
  установленный пакет, проверил draft JSON round-trip, переход в Config/project
  со стабильным ID и наличие autosave HTML asset: PASS.
- Independent Python review: сначала выявил ID rename, explicit unset и city
  counts; они исправлены и получили тесты. Повторное/final delta review: Approve,
  без CRITICAL/HIGH/MEDIUM замечаний. Targeted reviewer run: 16 passed.

### Приёмка требований

- STAFF-001: независимые график/дежурства, 5/2+дежурства и unchanged Config
  validation проверены unit и browser selectors traceability.
- STAFF-002: пустой старт, city lists, trim/blank lines, запятые, duplicate errors
  и отсутствие _DEFAULT_ROWS подтверждаются parser/unit/browser проверками.
- STAFF-003: незаданные/частичные роли, массовое изменение одного поля,
  независимые счётчики и explicit reset проверяются meaningful unit/browser tests.
- STAFF-004: spy запрещает запуск поиска для неполного draft; валидный Config
  требует прежнюю минимальную команду; неверное продолжение сохраняет персонал.
  Первый расчёт выполняется без pins и без подмены генератора.
- STAFF-005: ID/reordering/rename, draft backup и reload проверены; browser
  conflict/quota/transition/corrupt fallback включены в полный UI прогон.
- STAFF-006: old project/YAML, malformed import, готовый проект и old period/
  revision workflows проверены targeted tests; Новый проект имеет отдельный ID,
  оставляет старую запись и доступен только после подтверждённого сохранения.

Ограничения: сохранность неприменённых форм не обещается; storage привязан к
тому же origin/браузеру; частичный draft не является Config и не запускает
поиск. Coverage по существующей конфигурации исключает UI modules; их поведение
проверяется отдельно unit и настоящими browser journeys. Test-only календарный
wrapper не применяется при обычном запуске и не меняет production fetch.
Реальная пользовательская приёмка и test/main promotion ещё не выполнялись.

## Итоговые стабильные gates перед delivery

- `uv run pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-fail-under=80 --tb=short`: exit0, **864 passed**, coverage **88.20%** (полный повтор после harness fixes). Число подтверждено collect-only того же набора: 864.
- `uv run pytest tests/ui/ -q --tb=short`: exit0, **31 passed** (полный повтор после двух harness fixes). Число подтверждено collect-only: 31.
- Ruff lint/format184files, mypy70files, scoped SDD/index и diff whitespace: PASS.
- Финальный независимый code-reviewer: APPROVE, 0 замечаний всех уровней; Python-reviewer: APPROVE.
- STAFF-001–006 закрыты реализацией и реальными selectors; T006 закрыта после full browser failure/conflict/backup checks. Осталась фиксация dev delivery в T009.

Рабочее дерево проверено на dev; перед delivery HEAD и origin/dev равны
c5616674f941a81344540e5f8f6d49546a3358fa. Ни feature branch, ни pointer feature.json
не создавались; test/main данным изменением ещё не обновлены.

## Dev delivery и закрытие контракта

2026-10-12: реализация доставлена commit
98426aa5b9c8d27ed97c9d1ceba9feaa5df01334 (`feat: add personnel onboarding before roster configuration`).
Staged SDD gate, diff whitespace и commit hooks (SDD, Ruff, format,
Conventional Commit) прошли. После коммита --base HEAD~1 и index --check прошли;
`git push origin dev` успешно отправил commit. Локальный dev и origin/dev
совпали, рабочее дерево было чистым. Обычный direct-dev push использует
действующую привилегию владельца для checks, которые GitHub запускает после push;
это не утверждение о зелёном CI нового SHA. Runtime подтверждён локальными gates.

T001–T009 закрыты; STAFF-001–006 проверены. Status complete означает реализованный
и проверенный объём с dev delivery. Документ закрытия доставляется отдельным
docs commit. CI нового SHA проверяется отдельно; test/main promotion не выполнен.

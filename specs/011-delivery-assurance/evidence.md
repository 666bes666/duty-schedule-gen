# Evidence: Проверки и проверяемая поставка

## 2026-10-10 — планирование

Исходный коммит f432613, dev, дерево до начала чистое. Продуктовый итог подтверждён
пользователем. Источники и действующие тесты изучены; реализация и итоговые gates
ещё не выполнены. Исторические результаты будут дополнены, а не переписаны.


## 2026-10-11 — реализация и независимое ревью

Setup использует frozen uv и explicit solver extra. Required solver workflow отвергает skips/empty JUnit. Бенчмарки проверяют ready и сравнивают реально восстановленный prior SHA baseline с mean:10%; promotion зависит от успешных gates. Main lint проверяет SDD linkage --base. Build проверяет installed wheel/native PDF, packaged-runtime выполняет API/UI без source mounts; tag/release — reusable dependencies того же SHA/version/manifest/checksum. Версия5.0.0 явно фиксирует несовместимый ready/export контракт старых входов без verified context.

Продуктовый контракт сохранён в decisions.md изменения004. Перед реализацией были spec/plan/tasks/traceability. Реальные регрессии выявили и закрыли shared approvals order, active-month dependency gaps, malformed changelog, per-period pins loss, What-if CalendarError, unavailable fairness pool и packaged smoke context.

Независимое ревью: domain_python_review (Python/domain), integration_code_review (UI/project integration), api_security_delivery_review (API/security/delivery). Исполнители не коммитили; root независимо просмотрел fixes, ревьюеры повторно проверили root fixes. Новых CRITICAL/HIGH в проверенной области не осталось. Исторический исход планирования выше сохранён.

## 2026-10-11T00:37:32+03:00 — локальные gates и проверенная поставка5.0.0

Платформа macOS arm64, Python3.12.12. Для uv использовано ранее синхронизированное
окружение `UV_PROJECT_ENVIRONMENT=/tmp/duty-deps-validation.F58RhU`,
`UV_NO_SYNC=1` и `uv run --no-sync`; это сохраняет frozen dependency resolution
и обходит локальную проблему флагов каталога .venv приложения Codex.
`SPECIFY_FEATURE_DIRECTORY=$PWD/specs/011-delivery-assurance`,
`SPECIFY_FEATURE_NO_PERSIST=1`; локальный feature.json не менялся. Native PDF
проверен с `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

| Реальная команда | Результат |
|---|---|
| `uv run --no-sync pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-report=term-missing --cov-report=json:/tmp/duty-sdd-coverage-delivery.json --cov-fail-under=80 --tb=short -o addopts=''` | 750passed, 290.50s; coverage 85.73% |
| `uv run --no-sync pytest tests/ui -q --no-cov --junitxml=/tmp/duty-ui-final.xml --tb=short -o addopts=''` | 7passed, 27.93s; actual generate/edit/check/download/reopen и failed import |
| Required solver selection из solver-tests.yml с JUnit + `scripts/check_junit.py` | 35passed без skips/пустой выборки, независимо проверено api_security_delivery_review |
| What-if/search/OpenAPI targeted selection | 29passed независимо; три новых fairness restrictions до исправления3failed |
| `uv run --no-sync python scripts/check_sdd.py --base f4326134433c9b1e8daca0a598cd88698920b9a0` | pass структуры и сопровождения diff; повторяется после завершения артефактов |
| `uv run --no-sync ruff check src/ tests/ scripts/` | All checks passed |
| `uv run --no-sync ruff format --check src/ tests/ scripts/` | 164files already formatted |
| `uv run --no-sync mypy src/ scripts/` | 65source files pass; повторяется для финальной метрики |
| `uv lock --offline` и `uv lock --check --offline` | 130packages; изменена только версия проекта4→5 в uv.lock |
| `uv run --no-sync python scripts/export_openapi.py` + snapshot test | pass; OpenAPI5.0.0, новые plan/revision операции и media types |

Предыдущие фактические прогоны сохраняются как история: первоначально были
38failures и coverage71.32%; после исправления фикстур/интеграции741passed
с80.75%; затем745passed с85.01%. Они не заменяют финальный исход750passed.

## Артефакты и дополнительные проверки

api_security_delivery_review независимо собрал final wheel/sdist5.0.0 в
`/tmp/duty-delivery-final-5.0.0-whatif/`, выполнил isolated offline installed smoke
из вне репозитория: CLI, live API, XLS, personal ICS/night8h, native PDF,
отказ forged ready. Отдельно installed what-if подтвердил five_two, blocked_off,
weekly_off; упакованный whatif_service.py побайтно совпадает с исходником.
Логи build.log, installed-smoke.log, installed-whatif.log, checksums.txt,
metadata.json сохранены в этом каталоге. Это dirty-tree проверка,
привязка к новому committed SHA локально не утверждается.

Wheel SHA256: `204e93d5cff7e9b4f2d7867dea0a5781a650e40b567fd02630df8297d7035d6b`.
sdist SHA256: `61342c7c73f9e4cef8415881ca7d8564095a5bc20df701b1549ab9b2f2a04ef3`.

Security reviewer: Bandit0findings, pip-audit изолированного окружения без известных
уязвимостей. Реальная восстановленная pytest-benchmark baseline выбрана0001_baseline;
намеренно замедленный следующий запуск завершился PerformanceRegression при
mean:10%. Корректный final benchmark selection3passed без skips; каждый benchmark
требует ready с полным календарём/историей. Это доказательство механики gate,
не сравнение релизной производительности разных ОС. При пустом новом cache namespace
первый успешный прогон устанавливает baseline; последующие сравниваются с priorSHA.

## Оставшиеся проверки и ограничения

Docker daemon локально недоступен (`docker info`: отсутствует socket); контейнерный
runtime локально не проверен. DEL-002/T003 и финальный remote evidence остаются
открыты до обязательного packaged-runtime CI. Матрица Linux/Windows/macOS и Python3.13
исполняется в CI; локально подтверждена macOS/Python3.12. Тег/release не создавались
локально. В CI публикация зависит от того же verifiedSHA и проверенного manifest/checksum.

Прежние ограничения baseline: Excel2016 не запускался, формулы проверены openpyxl;
PDF functional smoke не доказывает качество печати любых команд. Арифметика costs
не является проверкой правового соответствия. Эти возможности не обещались новым
контрактом.

## Финальная проверка перед первым push

После завершения feature-артефактов повторно выполнены SDD --base f432613:
pass, Ruff check: pass, format:164files pass, mypy:65sourcefiles pass.
Git diff --check: pass; ветка dev и origin/dev до коммита совпадают.
Исходники после финального прогона750tests больше не менялись; менялись только
планы, traceability, evidence и пользовательская документация.

## 2026-10-11T08:24:11+03:00 — контейнерный runtime и CI: ограничение закрыто

Установленный Docker Desktop запущен без дополнительных разрешений; docker server29.8.1.
`docker build -t duty-schedule-sdd:8247ddb .` завершился0. Runtime imagearm64:
`sha256:ccc17dff0a928eb6c53fbf8fccd161ee48fc904df5282e4c3a66a63816dcec9e`.
Сборка из committed source8247ddbdc8efe23dc389e17cf4d23922719552c9.

- `uv run --no-sync python scripts/container_smoke.py --image duty-schedule-sdd:8247ddb`: exit0; реальная генерация/API/XLS/ICS/PDF и отказ forged-ready без source mounts.
- `docker run --rm -d --name duty-sdd-ui-8247ddb -p 127.0.0.1:0:8501 duty-schedule-sdd:8247ddb`: штатный packaged UI, healthhealthy.
- `scripts/container_smoke.py --ui-url http://<observed-loopback-port>`: exit0.
- `DUTY_TEST_STREAMLIT_URL=http://<observed-loopback-port> uv run --no-sync pytest tests/ui/test_project_journey.py -q --no-cov --junitxml=/tmp/duty-packaged-ui.xml --tb=short -o addopts=''`: 2passed,14.17s; реальная правка/проверка/скачивание/повторное открытие и atomic failed import.
- `scripts/check_junit.py /tmp/duty-packaged-ui.xml`: verified2executedtests без skips.

Логи: /tmp/duty-docker-build.log, /tmp/duty-container-api.log, /tmp/duty-packaged-ui.log.
Оба созданных smoke-контейнера удалены после проверки; образ оставлен для повторения.
Локальный runtime теперь подтверждён; предыдущая запись о недоступном daemon выше
сохраняется как исторический исход, не текущее ограничение.

GitHub на том же sourceSHA:
[CI Dev](https://github.com/666bes666/duty-schedule-gen/actions/runs/38113681686),
[SDD Gate](https://github.com/666bes666/duty-schedule-gen/actions/runs/38113683368),
[CI Test](https://github.com/666bes666/duty-schedule-gen/actions/runs/38113683396): success.
Последний включает Ubuntu/Windows Python3.12/3.13, security, performance, requiredsolver
без skips, lint/mypy и Streamlit. Benchmark promotion skipped на pull_request ожидаем.

T003/T005 закрыты фактическими runtime/CI результатами. Все DEL-001..004 реализованы
и проверены; complete относится к разработке и проверкам. PR66 вtest обновлён.
GitHub reviewDecision=REVIEW_REQUIRED и mergeStateStatus=BLOCKED: продвижение
веток/публикация ещё не выполнены; approving review требуется правилами GitHub.
Это отдельный шаг доставки, не незавершённая реализация требования.

## 2026-10-11T08:33:08+03:00 — итоговое ревью документов

Независимое содержательное ревью одобрило 33 уникальных требования изменений
003–011: ссылки на тесты существуют, критерии согласованы с реализацией,
незакрытых задач и замечаний CRITICAL/HIGH/MEDIUM нет. Уточнено руководство:
таблица UI «История» задаёт последний статус и рабочую серию; дополнительные
счётчики доступны через YAML/XLS и сохраняются в проекте.

Повторные проверки текущего дерева: SDD `--base f4326134433c9b1e8daca0a598cd88698920b9a0`,
Ruff check, Ruff format (164 файла), mypy (65 файлов), `git diff --check` — pass.
После общего прогона 750 tests / coverage 85.73% runtime source не изменялся;
финальный diff содержит только семь файлов спецификации, evidence и руководства.

## 2026-10-11 — миграция к строгому SDD и явная приёмка

Область `files` восстановлена из плана и реальных файлов. Это актуализация
живого контракта, а не утверждение о ретроспективном прохождении нового gate.

| ID | Проверяющие тесты | Evidence |
|---|---|---|
| DEL-001 | `tests/unit/test_delivery_workflows.py::test_required_test_report_rejects_missing_or_unexecuted_tests`, `tests/unit/test_solver.py`, `tests/unit/test_planning_rules.py`, `tests/unit/test_search_outcomes.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| DEL-002 | `tests/unit/test_delivery_workflows.py::test_packaged_smoke_payload_generates_ready`, `tests/ui/test_project_journey.py`, `tests/unit/test_cli_project.py`, `tests/e2e/test_cli_workflow.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| DEL-003 | `tests/unit/test_delivery_workflows.py::test_previous_sha_benchmark_is_selected_without_exact_cache_hit`, `tests/unit/test_delivery_workflows.py::test_main_release_compares_previous_success_and_promotes_after_all_gates`, `tests/performance/test_scheduler_benchmark.py` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |
| DEL-004 | `tests/unit/test_delivery_workflows.py::test_release_verifies_same_sha_version_and_bytes`, `tests/unit/test_delivery_workflows.py::test_release_rejects_existing_tag_for_other_sha`, `tests/unit/test_delivery_workflows.py::test_release_graph_requires_all_verified_artifact_gates` | Связи проверены; результаты исходных прогонов сохранены выше. Актуальный повторный прогон: [аудит012](../012-project-audit/evidence.md). |


## 2026-10-13 — macOS CI repair перед продвижением до main

Поручение: «внедряй до main». PR67 dev→test смерженd926d72; PR68 test→main
запущен. Main CI38385340188: обаMac Python3.12/3.13 exit139 в CFFI/WeasyPrint
_dlopen при test_real_streamlit_project_edit_check_and_reopen, остальные доступные
матрицы/UI/system/solver/security/performance прошли, build/container были skipped
из-за Mac failure. Логиjobs115255614485/115255614561 прочитаны; исторический fail
сохраняется, main пока не смержен.

DEL-001/plan/tasks/traceability и analysis переоткрыты до CI/test изменений.
Новая проверкаtest_macos_native_pdf_precedes_full_regression сначала RED
(StopIteration: отсутствует nativeMac step), затем GREEN. Только macOS устанавливает
Pango, передаёт brew library path черезDUTY_NATIVE_LIBRARY_PATH, экспортируетDYLD
внутриshell передsmoke/pytest. РеальныйPDF smoke обязательный; исходные матрица,
pytest аргументы, coverage>=80 и AppTest сохранены. Ни skip, ни stub не добавлены.

Официальная рекомендация о native path:
https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#missing-library

Локально UV_PROJECT_ENVIRONMENT=/tmp/duty-specs-20261011,
DYLD_FALLBACK_LIBRARY_PATH=$(brew --prefix)/lib:

- Native HTML.write_pdf smoke: PASS,3823bytes, PDFheader/nonempty.
- delivery workflows + исходный failing AppTest:14passed.
- full non-UI876collected/passed, exit0, coverage88.26%.
- Ruff/check/format, mypy71files, project_context/check_sdd/diff checks: PASS.
- General и Python review APPROVE; E501 исправлен formatter до коммита.

Настоящие Mac CI обоих Python остаются обязательным критерием T009; контракт
покаin-progress. Исправление доставляется обычным dev→test→main без обхода CI.

## 2026-10-16 — повторная проверка перед отправкой исправления

После возобновления поручения «продолжай внедрение до main» выполнен `git fetch
origin`: dev=d2871e0, test=d926d72, main=d713dc6. PR68 открыт; исходный macOS run
38385340188 завершён с failure. Pending merge origin/test в dev сохранён.

В новом изолированном окружении `/tmp/duty-main-20261016` выполнено
`uv sync --locked --dev --extra solver --group ci-perf`. С
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` реальный PDF smoke дал 3823 bytes,
а `uv run pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-report=term
--cov-fail-under=80` завершился с exit 0: 876 тестов, покрытие 88.28%.
Ruff check/format (187 файлов), mypy (71 файл), SDD `--base HEAD`, индекс и
`git diff --check` прошли. Платформенный критерий T009 остаётся открытым до
успешного исполнения исправленного macOS CI с обеими версиями Python.

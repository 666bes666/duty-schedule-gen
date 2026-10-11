# Evidence аудита

## 2026-10-11 — исходный аудит и планирование

Исходный HEAD f5ae141bffde227e7f005052832b87de8595dc37; dev=origin/dev, дерево
чистое. Изучены конституция, AGENTS/CLAUDE, CONTRIBUTING, все feature spec и
traceability, исходники затронутых границ, тесты и действующие workflows.
12каталогов: baseline27требований, изменения001–01144требования, закрытые задачи.

- `uv run python scripts/check_sdd.py`: pass исходного структурного gate.
- `uv run ruff check src/ tests/ scripts/ app.py api_main.py`: pass.
- `uv run ruff format --check src/ tests/ scripts/ app.py api_main.py`:166files pass.
- `uv run mypy src/ scripts/`:65sourcefiles pass.
- `uv run bandit -r src/ -c pyproject.toml -f json -o /tmp/duty-audit-bandit.json`:0findings.
- `uv run pip-audit --skip-editable --format json --output /tmp/duty-audit-dependencies.json`: no known vulnerabilities.
- `uvx --from vulture vulture src scripts app.py api_main.py --min-confidence 100`:
  unused kwargs logging callback и employees_df dashboard; callback signature
  используется logging и не удаляется.

Первый pytest завершился ImportError (editable package отсутствовал после
синхронизации окружения); `uv sync --locked --all-groups --extra solver
--reinstall-package duty-schedule` исправил окружение. Это не результат тестов.
Повторный full pytest запущен; итог будет добавлен отдельной записью.

GitHub: dev/test/main protected, но `Specifications and API contract` отсутствует
в required checks; main требует retired `Lint + Mypy` и `Build`. PR66 dev→test
уже открыт. Review count=1 сохраняется. CodeRabbit CLI отсутствует; этим сервисом
ревью не выполнялось. Исторические evidence прежних изменений сохраняются.

Артефакты012 подготовлены до реализации. Приёмка пока не завершена.

## 2026-10-11 — окончательная реализация и проверка

Окружение: macOS arm64, Python3.12.12, locked dependencies. Рабочая ignored .venv
имеет UF_HIDDEN на .pth; Python site.py явно пропускает такие файлы. Повторный
reinstall не устранил это свойство Codex checkout, поэтому прогоны использовали
новое `UV_PROJECT_ENVIRONMENT=/tmp/duty-project-audit-20261011` после
`uv sync --locked --all-groups --extra solver`, затем `uv run --no-sync`.
Это исправление описания первоначального ImportError выше: успешный reinstall
сам по себе не восстановил import. Для cold clone использована собственная новая
.venv, без этого обхода. SPECIFY_FEATURE_NO_PERSIST=1; feature.json не записывался.

| Фактическая команда / проверка | Результат |
|---|---|
| `uv run --no-sync pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-report=json:/tmp/duty-audit-coverage-final.json --cov-fail-under=80 --junitxml=/tmp/duty-audit-final.xml --tb=short` | 794passed,0failures,0errors,0skips; coverage87.6441753171857% |
| `uv run --no-sync pytest tests/ui -q --junitxml=/tmp/duty-audit-ui.xml --tb=short` | 7passed,0skips; actual UI journeys |
| SDD/index subprocess tests с coverage.process_startup + `coverage combine/report/json` | check_sdd89%, project_context95%, combined91.24579124579125%; 66data files combined,22duplicates skipped |
| `uv run --no-sync ruff check src/ tests/ scripts/ app.py api_main.py` | All checks passed |
| `uv run --no-sync ruff format --check src/ tests/ scripts/ app.py api_main.py` | 168files formatted |
| `uv run --no-sync mypy src/ scripts/` | 66sourcefiles pass |
| `uv run --no-sync python scripts/check_sdd.py --base f5ae141bffde227e7f005052832b87de8595dc37` | pass exact scope текущего изменения |
| `check_sdd.py --base origin/test` и `--base origin/main` | сначала обнаружены15путей исторической интеграции без scope; отнесены к правильным живым контрактам/планам, повторно оба pass |
| `uv run --no-sync python scripts/check_sdd.py --staged` | pass снимка будущего коммита; tests доказывают отказ unstaged подмены |
| `uv run --no-sync python scripts/project_context.py --check` | pass после регенерации; отсутствующих definitions нет по независимому AST сравнению |
| `git diff --check` | pass |
| `uv build --out-dir /tmp/duty-audit-dist` | wheel/sdist5.0.0 собраны |
| `uv run --no-project --with '/tmp/duty-audit-dist/duty_schedule-5.0.0-py3-none-any.whl[solver]' python scripts/artifact_smoke.py --source-root "$PWD"` | Installed wheel CLI/API smoke passed5.0.0; export/XLS/ICS/PDF/forged-ready проверены |
| `docker build -t duty-schedule-audit:20261011 .` | exit0; image sha256:ab3406e21060d054d1c360d2fb09f193784188e40fafb5a5b2879bebb9558b70 |
| `scripts/container_smoke.py --image duty-schedule-audit:20261011` | exit0; функциональный API/export smoke без source mounts |
| `scripts/container_smoke.py --ui-url http://127.0.0.1:55001` | exit0; healthy packaged UI |
| `DUTY_TEST_STREAMLIT_URL=http://127.0.0.1:55001 uv run --no-sync pytest tests/ui/test_project_journey.py -q --junitxml=/tmp/duty-audit-packaged-ui.xml` | 2passed,0skips; edit/check/download/reopen и failed import |

Full pytest и UI использовали DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib для
уже установленного native PDF. Tooling coverage instrumentation создавалась лишь
в новом /tmp окружении и удалена после прогона. Smoke containers этого аудита
удалены; образ сохранён. Wheel/container — проверки frozen dirty/staged дерева,
их привязка к будущему committed SHA не утверждается; эту связь подтверждает CI.
Логи/JSON/XML: /tmp/duty-project-audit-tests-final.log, /tmp/duty-audit-final.xml,
/tmp/duty-audit-coverage-final.json, /tmp/duty-audit-ui.xml,
/tmp/duty-audit-toolcov/report.json, /tmp/duty-audit-installed.log,
/tmp/duty-audit-docker-build.log, /tmp/duty-audit-container-api.log,
/tmp/duty-audit-packaged-ui.xml.

## Негативные регрессии и независимое ревью

До реализации 24новых отрицательных сценария SDD давали ошибочный pass и
завершились24failures/1positive. Исправлены scope/все типы файлов, worktree/untracked,
staged snapshot, IDs/tasks/evidence, пустые/невалидные/несобираемые tests.
Ревью выявило дополнительные реальные контрпримеры: ignored metadata/schema,
произвольный YAML в specs, __test__/fixtures/annotations/inherited constructor,
external symlink scope, leading-space filenames, nested/conditional definitions.
Соответствующие regressions сначала воспроизводили failure, после fixes проходят.
Нормальные fixtures/disabled modules не объявляются успешной приёмкой.

Независимые read-only reviewers: audit_python_review (python-reviewer) и
 audit_contract_review (code-reviewer), workflow ecc:source-command-review-pr.
Оба дали APPROVE после повторной проверки исправлений; открытых CRITICAL/HIGH/
MEDIUM нет. Python reviewer проверил106tooling/constraints tests, Ruff/format/mypy,
exact scope и полное совпадение индексируемых definitions. Contract reviewer
дополнительно проверил project/history/calendar/export-time/pipeline/revision API,
контракт001 и release graph. Reviewers не меняли файлы и не создавали коммитов.
CodeRabbit CLI отсутствует; CodeRabbit review не выполнялось.

## Холодный старт

Отдельный источник создан из staged snapshot через checkout-index, локальный
commit и `git clone --no-local --branch dev`. Snapshot tree:
425b420c3bb62fdf1d1367d7d1945959b287515e; clone commit:
9bc75b63cd036451cb9acf6735db9aa90053bca9. Это disposable verification repository,
не коммит основной dev и не GitHub commit.
Clone: /var/folders/fc/spq8fqk902q_x3mqx2g_4gl80000gn/T/duty-audit-cold-clone-pcysg00h/repo.

- `uv sync --locked --dev --extra solver`: новая .venv,102packages, import работает.
- `uv run --no-sync python scripts/project_context.py --feature 012-project-audit`:
  live dev/SHA/clean/статусы/команды; локальный указатель не создан.
- `check_sdd.py` и `project_context.py --check`: оба pass.
- `uv run --no-sync pytest tests/unit/test_sdd.py tests/unit/test_project_context.py tests/contract/test_openapi_snapshot.py -q --junitxml=/tmp/duty-audit-cold-tests.xml`:
  70passed,0failures,0errors,0skips.
- `uv run --no-sync pre-commit install --install-hooks`: pass.
- `uv run --no-sync pre-commit run --all-files`: SDD/Ruff/format pass.
- `git status --short`: пусто. Чужие/старые /tmp окружения не использовались.

После cold snapshot менялись только планы/scope/evidence/status и generated index;
реализация, тесты и lock больше не менялись. Это ограничение точности snapshot
сохранено; свежий GitHub sourceSHA может быть проверен отдельным новым clone.

## Приёмка требований

| ID | Реальные доказательства | Исход |
|---|---|---|
| AUD-001 | Negative/scoped/staged tests, SDD --base original/test/main, snapshot | pass |
| AUD-002 | Bidirectional IDs/T-ID/test nodes/per-ID evidence, все13каталогов | pass |
| AUD-003 | Конституция1.1.0/инструкции/templates, hook/CI/release graph regression | pass |
| AUD-004 | deterministic complete Git/AST index, ignored/schema/path/drift tests, reviewer AST comparison | pass |
| AUD-005 | новый isolated clone+venv,70tests, context/index/SDD/hooks/clean status | pass |
| AUD-006 | deleted retired builders/stub/archive, current6scenarios, full794+UI7+packaged2 | pass |
| AUD-007 | audit.md, независимые APPROVE, full checks/security/build/runtime, live required checks; доставка ещё ожидает новый CI и approving review | implementation pass; delivery open |

## GitHub: обязательные проверки

Live GitHub required status checks обновлены на dev/test/main и привязаны к
GitHub Actions app15368. Старые main Lint+Mypy/Build заменены действующими names;
solver, packaged-runtime, release performance и SDD обязательны. strict=true
сохранён. Полные before/after checks: [github-protection.json](github-protection.json).
Число approving reviews, admin enforcement, force push/deletion и остальные
поля защиты сравнены побайтно как JSON и не менялись. Защита сохраняет count1
для test/main; repo auto-merge выключен. Администраторский override не выполнен.
Текущий PR66 и старый CI не являются evidence нового audit SHA.
T001–T007 закрыты проверками. T008 и status in-progress остаются до фактической
доставки; это честное состояние, а не пропущенный артефакт.

# Холодный старт разработчика и агента

Репозиторий содержит полный контекст без памяти предыдущего чата. Read-only вход:
AGENTS → конституция → SDD → индекс → выбранные spec/plan/tasks/traceability/evidence
→ реальные исходники/тесты. История baseline не заменяет текущие feature contracts.

## Чистый clone

```bash
git clone https://github.com/666bes666/duty-schedule-gen.git
cd duty-schedule-gen
git switch dev
uv sync --locked --dev --extra solver
uv run python scripts/project_context.py
uv run python scripts/check_sdd.py
uv run python scripts/project_context.py --check
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type commit-msg
```

Python3.12+ и uv обязательны. `solver` нужен для проверки поставляемого CP-SAT;
обычный runtime также допускает greedy без extra. Locked sync должен завершиться
до параллельных запусков проверок; не запускайте одновременно sync/build editable
окружения. Контекст показывает живые branch/SHA/dirty, версии, статусы требований и
незакрытые задачи. Работа разрешена только в dev; чужие изменения сохраняются.

В некоторых macOS Codex checkout все файлы ignored `.venv` получают UF_HIDDEN.
Python пропускает hidden `.pth`, поэтому editable import может не работать даже
после успешного sync. При подтверждённом случае используйте отдельное окружение:

```bash
export UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/duty-schedule-dev-venv"
uv sync --locked --dev --extra solver
uv run python -c 'import duty_schedule; print(duty_schedule.__version__)'
```

Это явная особенность локального окружения. Чистый clone проверяется отдельно;
не используйте прежний /tmp каталог как доказательство cold start нового дерева.

## Выбор изменения

```bash
uv run python scripts/project_context.py --feature 012-project-audit
export SPECIFY_FEATURE_DIRECTORY="$PWD/specs/012-project-audit"
export SPECIFY_FEATURE_NO_PERSIST=1
```

Для нового изменения сначала создайте отдельную specs/NNN-name спецификацию по
[SDD](sdd.md); замените путь на неё. Не записывайте feature.json и не создавайте
feature-ветку. Ни hotfix, ни cleanup, ни изменение docs/CI не разрешены вне SDD.
В traceability `files` перечислите каждый изменяемый путь; новые файлы расширяют
область до реализации. Изменение смысла старого требования сохраняет ID и
возвращает контракт в рабочий статус, с новой записью evidence.

## Реализация и проверка

```bash
uv run python scripts/check_sdd.py --base HEAD
uv run python scripts/project_context.py --write
uv run python scripts/project_context.py --check
uv run ruff check src/ tests/ scripts/ app.py api_main.py
uv run ruff format --check src/ tests/ scripts/ app.py api_main.py
uv run mypy src/ scripts/
uv run pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-fail-under=80
```

Для всех уровней CI: `uv sync --locked --all-groups --extra solver`.
UI: `uv run playwright install chromium`, затем `uv run pytest tests/ui -q`.
PDF на macOS требует native Pango; если Homebrew библиотеки уже установлены,
проверки можно запускать с `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
В Ubuntu CI/контейнере библиотеки устанавливаются действующими workflow/Dockerfile.

## Коммит и доставка

Сначала проверьте состав diff и ветку, stage только свои файлы, затем:

```bash
uv run python scripts/check_sdd.py --staged
git diff --cached --check
```

Staged gate проверяет именно файлы будущего коммита. Подготовленный на диске, но
не добавленный в index документ не разрешает код. После Conventional Commit в
`dev` немедленно push; committed diff проверяется с `--base HEAD~1` перед push.
Далее зелёный CI → GitHub PR dev→test → зелёный CI → GitHub PR test→main.
Approving review и required status checks не обходятся. Незавершённая доставка
остаётся явной задачей и не превращается в complete по обещанию.

## Где искать

- [Полный индекс](project-index.md), [машинный индекс](project-index.json).
- [Архитектура](../ARCHITECTURE.md), [руководство составителя](scheduling-workflow.md).
- [Текущие контракты](../specs/), [аудит012](../specs/012-project-audit/audit.md).
- [Правила вклада](../CONTRIBUTING.md), [CI](../.github/workflows/).

Индекс не содержит локальных outputs/caches/secrets и не исполняет исходники.
Его JSON schema_version=1; нет self hashes и временных отметок. Проверка drift
сравнивает пути/symbols/imports/контракты, а актуальное состояние Git выводится live.

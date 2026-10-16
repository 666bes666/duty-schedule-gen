# Проверка 019 — 2026-10-12

Окружение: macOS ARM, Python 3.12.12, UV_PROJECT_ENVIRONMENT=/tmp/duty-specs-20261011,
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib. SPECIFY_FEATURE_DIRECTORY задан для 019,
SPECIFY_FEATURE_NO_PERSIST=1; указатель feature.json не менялся. Ветка dev.

## Выполненные проверки

- ui-ux-pro-max design-system/UX searches, read-only аудит localhost:8504;
  исходные проблемы и решения в analysis.md. Демонстрационные данные отдельно на8505.
- `uv run pytest tests/ -q --ignore=tests/ui --cov=duty_schedule --cov-fail-under=80 --tb=short`
  — exit0, 868 collected, coverage88.24%. После последнего изменения вкладок/компоновки
  `pytest tests/unit/test_personnel_onboarding.py tests/unit/test_ui_workflow.py
  tests/unit/test_product_integrity.py -q --tb=short` — exit0,51 tests.
- Новые browser tests smooth_authoring — 4 passed (city+pending+reload, navigation,
  light/dark theme harness и мобильный экран375px с клавиатурным назначением).
- Первый fullUI:33 passed,3 failed. Два теста требовали раскрыть перемещённые
  детали/расширенный расчёт; третий выявил сброс result tab при rerun. Исправлено
  stateful result selection, критерий UX-003 уточнён до исправления. Targeted
  first_month/replanning/project_journey —5 passed. Последний `uv run pytest tests/ui/ -q --tb=short` — exit0,36 tests passed.
- Предварительно исправлены: ошибки mypy из-за повторных локальных переменных;
  AppTest выбирал неверный DataFrame/escaped columns, исправлен semantic selector.
  Dropdown периода после длинного персонала: test viewport2000px, обычный выбор option;
  мобильный путь проверяется отдельно с viewport375px. Тест не подменяет значение.
- `uv run ruff check src/ tests/ scripts/ app.py` — pass;
  `ruff format --check src/ tests/ scripts/ app.py` —186 files formatted;
  `mypy src/ scripts/` —70 files, pass.
- `uv build --wheel --out-dir /tmp/duty-ux-wheel` — pass; HTML моста в wheel побайтно
  совпадает с исходным themed component.
- SDD --base HEAD и project_context --write — pass; финальные staged/index gates проверяются перед коммитом.

## Содержательное ревью

Python reviewer: pending guard атомарен, скрытые поля сохраняются, navigation target
применяется до stateful tabs; role_notice привязан к snapshot. Итог APPROVE.
Code reviewer: финальные stateful result tabs, compact queue и advanced controls — APPROVE.
JS reviewer: theme после source/type guard; token/hash/locks/storage не меняются,
style assignment не вводит HTML injection; node --check pass, APPROVE.

## Приёмка

- UX-001: unit rejects empty/unknown/mixed configured IDs атомарно, partial rows pending;
  browser показывает только оставшихся после назначения города/reload.
- UX-002: unit проверяет все4 сочетания, ID/roundtrip; browser one profile click +continue
  для общей команды, персональная независимость полей/частичный draft сохранены.
- UX-003: период сохраняется при едином переходе; readiness выше tabs, переход действительно
  выбирает историю; advanced capabilities и путь первого месяца до XLS проверены.
- UX-004: AppTest проверяет label, column_order и сохранение always_on_duty/morning_only/ID;
  underlying keys/formats и scheduler rules не менялись.
- UX-005: browser375px без page-wide overflow,44px buttons, Enter применяет профиль;
  iframe computed colors совпадают с light/dark palettes. Тема по официальному протоколу:
  https://docs.streamlit.io/develop/concepts/custom-components/components-v1/intro

## Ограничения

Продуктовые API/solver/экспорт не менялись. Нативный PDF проверен общей регрессией наmacOS;
другие ОС локально не запускались. Dev preview перезапущен с fileWatcherType=none:
горячая перезагрузка моделей держала старые классы в session_state; сохранённые browser
данные не менялись и восстановлены при новом процессе. test/main не продвинуты.

## Финальная приёмка

Все UX-001–005 выполнены по перечисленным тестам. Финальный browser suite36/36,
повторные targeted unit51/51, mypy и Ruff успешны. На native CUA проверено назначение
Москвы: прогресс4/6, в очереди только2 сотрудника Хабаровска. Снимок демонстрационных
данных /tmp/duty-ux-role-queue.jpg. Рабочий localhost:8504 восстановил существующий
проект без изменения имён/ролей и показывает новую таблицу/готовность; ошибки нет.

Финальные проверки: `check_sdd.py --base HEAD`, `check_sdd.py --staged`,
`project_context.py --check`, `git diff --cached --check` — pass.
Ruff check/format и mypy повторены на финальном дереве — pass (186/70 файлов).

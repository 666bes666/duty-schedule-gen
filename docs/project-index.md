# Индекс проекта

Генерируется `uv run python scripts/project_context.py --write`; ручные изменения запрещены.
Версия приложения: 5.0.0. Файлов: 374. Полные symbols/imports/traceability: [JSON](project-index.json).

Холодный старт: [руководство](cold-start.md). Правила: [AGENTS](../AGENTS.md), [SDD](sdd.md), [конституция](../.specify/memory/constitution.md).

## Карта областей

| Область | Файлов |
|---|---:|
| api | 14 |
| claude_instructions | 10 |
| codex_instructions | 10 |
| delivery | 10 |
| documentation | 5 |
| domain | 15 |
| export | 5 |
| project | 20 |
| scheduler | 19 |
| sdd_contract | 108 |
| sdd_toolkit | 25 |
| tests | 115 |
| tooling | 8 |
| ui | 10 |

## Спецификации и требования

| Спецификация | Статус | Требования |
|---|---|---|
| [specs/000-baseline](../specs/000-baseline/spec.md) | recorded | CFG-001, CFG-002, CFG-003, CFG-004, SCH-001, SCH-002, SCH-003, SCH-004, SCH-005, SCH-006, SCH-007, SCH-008, SCH-009, SCH-010, SCH-011, EXP-001, EXP-002, EXP-003, EXP-004, EXP-005, CLI-001, CLI-002, UI-001, UI-002, API-001, API-002, API-003 |
| [specs/001-sdd-adoption](../specs/001-sdd-adoption/spec.md) | complete | SDD-001, SDD-002, SDD-003, SDD-004, SDD-005, SDD-006 |
| [specs/002-dependency-update](../specs/002-dependency-update/spec.md) | complete | DEP-001, DEP-002, DEP-003, DEP-004, DEP-005 |
| [specs/003-secure-api-exports](../specs/003-secure-api-exports/spec.md) | complete | SEC-001, SEC-002, SEC-003 |
| [specs/004-scheduling-validity](../specs/004-scheduling-validity/spec.md) | complete | VALID-001, VALID-002, VALID-003, VALID-004 |
| [specs/005-postprocess-integrity](../specs/005-postprocess-integrity/spec.md) | complete | POST-001, POST-002, POST-003 |
| [specs/006-month-continuity](../specs/006-month-continuity/spec.md) | complete | HIST-001, HIST-002, HIST-003, HIST-004 |
| [specs/007-calendar-shift-model](../specs/007-calendar-shift-model/spec.md) | complete | TIME-001, TIME-002, TIME-003 |
| [specs/008-workload-quality](../specs/008-workload-quality/spec.md) | complete | HOURS-001, HOURS-002, HOURS-003, HOURS-004, HOURS-005 |
| [specs/009-schedule-revisions](../specs/009-schedule-revisions/spec.md) | complete | REV-001, REV-002, REV-003, REV-004, REV-005 |
| [specs/010-ui-configuration](../specs/010-ui-configuration/spec.md) | complete | UIC-001, UIC-002, UIC-003, UIC-004, UIC-005, UIC-006 |
| [specs/011-delivery-assurance](../specs/011-delivery-assurance/spec.md) | complete | DEL-001, DEL-002, DEL-003, DEL-004 |
| [specs/012-project-audit](../specs/012-project-audit/spec.md) | complete | AUD-001, AUD-002, AUD-003, AUD-004, AUD-005, AUD-006, AUD-007 |
| [specs/013-product-logic-audit](../specs/013-product-logic-audit/spec.md) | complete | PAUD-001, PAUD-002, PAUD-003, PAUD-004, PAUD-005 |
| [specs/014-product-reliability](../specs/014-product-reliability/spec.md) | complete | DATA-001, DATA-002, DATA-003, DATA-004, DATA-005 |
| [specs/015-guided-authoring](../specs/015-guided-authoring/spec.md) | complete | FLOW-001, FLOW-002, FLOW-003, FLOW-004 |
| [specs/016-stable-replanning](../specs/016-stable-replanning/spec.md) | complete | REPAIR-001, REPAIR-002 |
| [specs/017-two-month-quality](../specs/017-two-month-quality/spec.md) | complete | QUALITY-001, QUALITY-002, QUALITY-003 |
| [specs/018-personnel-onboarding](../specs/018-personnel-onboarding/spec.md) | complete | STAFF-001, STAFF-002, STAFF-003, STAFF-004, STAFF-005, STAFF-006 |
| [specs/019-smooth-authoring](../specs/019-smooth-authoring/spec.md) | complete | UX-001, UX-002, UX-003, UX-004, UX-005 |

## API операции

| Метод | Путь | Operation ID |
|---|---|---|
| POST | `/api/v1/config/validate` | validate_config_api_v1_config_validate_post |
| POST | `/api/v1/export/ics` | export_ics_endpoint_api_v1_export_ics_post |
| POST | `/api/v1/export/pdf` | export_pdf_endpoint_api_v1_export_pdf_post |
| POST | `/api/v1/export/revision/ics` | export_revision_ics_api_v1_export_revision_ics_post |
| POST | `/api/v1/export/revision/pdf` | export_revision_pdf_api_v1_export_revision_pdf_post |
| POST | `/api/v1/export/revision/xls` | export_revision_xls_api_v1_export_revision_xls_post |
| POST | `/api/v1/export/xls` | export_xls_endpoint_api_v1_export_xls_post |
| GET | `/api/v1/holidays/{year}/{month}` | get_holidays_api_v1_holidays__year___month__get |
| POST | `/api/v1/schedule/generate` | generate_api_v1_schedule_generate_post |
| POST | `/api/v1/schedule/generate-range` | generate_range_api_v1_schedule_generate_range_post |
| POST | `/api/v1/schedule/plan` | plan_api_v1_schedule_plan_post |
| POST | `/api/v1/schedule/stats` | stats_api_v1_schedule_stats_post |
| POST | `/api/v1/whatif/compare` | compare_scenarios_api_v1_whatif_compare_post |

## Все файлы

| Путь | Область |
|---|---|
| [.agents/skills/speckit-analyze/SKILL.md](../.agents/skills/speckit-analyze/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-checklist/SKILL.md](../.agents/skills/speckit-checklist/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-clarify/SKILL.md](../.agents/skills/speckit-clarify/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-constitution/SKILL.md](../.agents/skills/speckit-constitution/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-converge/SKILL.md](../.agents/skills/speckit-converge/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-implement/SKILL.md](../.agents/skills/speckit-implement/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-plan/SKILL.md](../.agents/skills/speckit-plan/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-specify/SKILL.md](../.agents/skills/speckit-specify/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-tasks/SKILL.md](../.agents/skills/speckit-tasks/SKILL.md) | codex_instructions |
| [.agents/skills/speckit-taskstoissues/SKILL.md](../.agents/skills/speckit-taskstoissues/SKILL.md) | codex_instructions |
| [.claude/skills/speckit-analyze/SKILL.md](../.claude/skills/speckit-analyze/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-checklist/SKILL.md](../.claude/skills/speckit-checklist/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-clarify/SKILL.md](../.claude/skills/speckit-clarify/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-constitution/SKILL.md](../.claude/skills/speckit-constitution/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-converge/SKILL.md](../.claude/skills/speckit-converge/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-implement/SKILL.md](../.claude/skills/speckit-implement/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-plan/SKILL.md](../.claude/skills/speckit-plan/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-specify/SKILL.md](../.claude/skills/speckit-specify/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-tasks/SKILL.md](../.claude/skills/speckit-tasks/SKILL.md) | claude_instructions |
| [.claude/skills/speckit-taskstoissues/SKILL.md](../.claude/skills/speckit-taskstoissues/SKILL.md) | claude_instructions |
| [.dockerignore](../.dockerignore) | project |
| [.env.example](../.env.example) | project |
| [.github/PULL_REQUEST_TEMPLATE.md](../.github/PULL_REQUEST_TEMPLATE.md) | delivery |
| [.github/actions/setup-python/action.yml](../.github/actions/setup-python/action.yml) | delivery |
| [.github/actions/streamlit-smoke/action.yml](../.github/actions/streamlit-smoke/action.yml) | delivery |
| [.github/workflows/ci-dev.yml](../.github/workflows/ci-dev.yml) | delivery |
| [.github/workflows/ci-main.yml](../.github/workflows/ci-main.yml) | delivery |
| [.github/workflows/ci-tag.yml](../.github/workflows/ci-tag.yml) | delivery |
| [.github/workflows/ci-test.yml](../.github/workflows/ci-test.yml) | delivery |
| [.github/workflows/release.yml](../.github/workflows/release.yml) | delivery |
| [.github/workflows/sdd.yml](../.github/workflows/sdd.yml) | delivery |
| [.github/workflows/solver-tests.yml](../.github/workflows/solver-tests.yml) | delivery |
| [.gitignore](../.gitignore) | project |
| [.pre-commit-config.yaml](../.pre-commit-config.yaml) | project |
| [.specify/.gitignore](../.specify/.gitignore) | sdd_toolkit |
| [.specify/LICENSE](../.specify/LICENSE) | sdd_toolkit |
| [.specify/UPSTREAM.md](../.specify/UPSTREAM.md) | sdd_toolkit |
| [.specify/init-options.json](../.specify/init-options.json) | sdd_toolkit |
| [.specify/integration.json](../.specify/integration.json) | sdd_toolkit |
| [.specify/integrations/claude.manifest.json](../.specify/integrations/claude.manifest.json) | sdd_toolkit |
| [.specify/integrations/codex.manifest.json](../.specify/integrations/codex.manifest.json) | sdd_toolkit |
| [.specify/integrations/speckit.manifest.json](../.specify/integrations/speckit.manifest.json) | sdd_toolkit |
| [.specify/memory/.constitution-template.json](../.specify/memory/.constitution-template.json) | sdd_toolkit |
| [.specify/memory/constitution.md](../.specify/memory/constitution.md) | sdd_toolkit |
| [.specify/scripts/bash/check-prerequisites.sh](../.specify/scripts/bash/check-prerequisites.sh) | sdd_toolkit |
| [.specify/scripts/bash/common.sh](../.specify/scripts/bash/common.sh) | sdd_toolkit |
| [.specify/scripts/bash/create-new-feature.sh](../.specify/scripts/bash/create-new-feature.sh) | sdd_toolkit |
| [.specify/scripts/bash/resolve-template.sh](../.specify/scripts/bash/resolve-template.sh) | sdd_toolkit |
| [.specify/scripts/bash/setup-plan.sh](../.specify/scripts/bash/setup-plan.sh) | sdd_toolkit |
| [.specify/scripts/bash/setup-tasks.sh](../.specify/scripts/bash/setup-tasks.sh) | sdd_toolkit |
| [.specify/templates/checklist-template.md](../.specify/templates/checklist-template.md) | sdd_toolkit |
| [.specify/templates/constitution-template.md](../.specify/templates/constitution-template.md) | sdd_toolkit |
| [.specify/templates/evidence-template.md](../.specify/templates/evidence-template.md) | sdd_toolkit |
| [.specify/templates/plan-template.md](../.specify/templates/plan-template.md) | sdd_toolkit |
| [.specify/templates/spec-template.md](../.specify/templates/spec-template.md) | sdd_toolkit |
| [.specify/templates/tasks-template.md](../.specify/templates/tasks-template.md) | sdd_toolkit |
| [.specify/templates/traceability-template.json](../.specify/templates/traceability-template.json) | sdd_toolkit |
| [.specify/workflows/speckit/workflow.yml](../.specify/workflows/speckit/workflow.yml) | sdd_toolkit |
| [.specify/workflows/workflow-registry.json](../.specify/workflows/workflow-registry.json) | sdd_toolkit |
| [.streamlit/config.toml](../.streamlit/config.toml) | project |
| [AGENTS.md](../AGENTS.md) | project |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | project |
| [CHANGELOG.md](../CHANGELOG.md) | project |
| [CLAUDE.md](../CLAUDE.md) | project |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | project |
| [Dockerfile](../Dockerfile) | project |
| [LICENSE](../LICENSE) | project |
| [README.md](../README.md) | project |
| [api_main.py](../api_main.py) | project |
| [app.py](../app.py) | project |
| [cliff.toml](../cliff.toml) | project |
| [config.example.yaml](../config.example.yaml) | project |
| [docker-compose.yml](../docker-compose.yml) | project |
| [docs/cold-start.md](../docs/cold-start.md) | documentation |
| [docs/project-index.json](../docs/project-index.json) | documentation |
| [docs/project-index.md](../docs/project-index.md) | documentation |
| [docs/scheduling-workflow.md](../docs/scheduling-workflow.md) | documentation |
| [docs/sdd.md](../docs/sdd.md) | documentation |
| [pyproject.toml](../pyproject.toml) | project |
| [scripts/artifact_manifest.py](../scripts/artifact_manifest.py) | tooling |
| [scripts/artifact_smoke.py](../scripts/artifact_smoke.py) | tooling |
| [scripts/benchmark_baseline.py](../scripts/benchmark_baseline.py) | tooling |
| [scripts/check_junit.py](../scripts/check_junit.py) | tooling |
| [scripts/check_sdd.py](../scripts/check_sdd.py) | tooling |
| [scripts/container_smoke.py](../scripts/container_smoke.py) | tooling |
| [scripts/export_openapi.py](../scripts/export_openapi.py) | tooling |
| [scripts/project_context.py](../scripts/project_context.py) | tooling |
| [specs/000-baseline/contracts/openapi.json](../specs/000-baseline/contracts/openapi.json) | sdd_contract |
| [specs/000-baseline/gaps.md](../specs/000-baseline/gaps.md) | sdd_contract |
| [specs/000-baseline/spec.md](../specs/000-baseline/spec.md) | sdd_contract |
| [specs/000-baseline/traceability.json](../specs/000-baseline/traceability.json) | sdd_contract |
| [specs/001-sdd-adoption/evidence.md](../specs/001-sdd-adoption/evidence.md) | sdd_contract |
| [specs/001-sdd-adoption/plan.md](../specs/001-sdd-adoption/plan.md) | sdd_contract |
| [specs/001-sdd-adoption/spec.md](../specs/001-sdd-adoption/spec.md) | sdd_contract |
| [specs/001-sdd-adoption/tasks.md](../specs/001-sdd-adoption/tasks.md) | sdd_contract |
| [specs/001-sdd-adoption/traceability.json](../specs/001-sdd-adoption/traceability.json) | sdd_contract |
| [specs/002-dependency-update/checklists/requirements.md](../specs/002-dependency-update/checklists/requirements.md) | sdd_contract |
| [specs/002-dependency-update/evidence.md](../specs/002-dependency-update/evidence.md) | sdd_contract |
| [specs/002-dependency-update/plan.md](../specs/002-dependency-update/plan.md) | sdd_contract |
| [specs/002-dependency-update/spec.md](../specs/002-dependency-update/spec.md) | sdd_contract |
| [specs/002-dependency-update/tasks.md](../specs/002-dependency-update/tasks.md) | sdd_contract |
| [specs/002-dependency-update/traceability.json](../specs/002-dependency-update/traceability.json) | sdd_contract |
| [specs/002-dependency-update/versions.json](../specs/002-dependency-update/versions.json) | sdd_contract |
| [specs/003-secure-api-exports/evidence.md](../specs/003-secure-api-exports/evidence.md) | sdd_contract |
| [specs/003-secure-api-exports/plan.md](../specs/003-secure-api-exports/plan.md) | sdd_contract |
| [specs/003-secure-api-exports/spec.md](../specs/003-secure-api-exports/spec.md) | sdd_contract |
| [specs/003-secure-api-exports/tasks.md](../specs/003-secure-api-exports/tasks.md) | sdd_contract |
| [specs/003-secure-api-exports/traceability.json](../specs/003-secure-api-exports/traceability.json) | sdd_contract |
| [specs/004-scheduling-validity/data-model.md](../specs/004-scheduling-validity/data-model.md) | sdd_contract |
| [specs/004-scheduling-validity/decisions.md](../specs/004-scheduling-validity/decisions.md) | sdd_contract |
| [specs/004-scheduling-validity/evidence.md](../specs/004-scheduling-validity/evidence.md) | sdd_contract |
| [specs/004-scheduling-validity/plan.md](../specs/004-scheduling-validity/plan.md) | sdd_contract |
| [specs/004-scheduling-validity/spec.md](../specs/004-scheduling-validity/spec.md) | sdd_contract |
| [specs/004-scheduling-validity/tasks.md](../specs/004-scheduling-validity/tasks.md) | sdd_contract |
| [specs/004-scheduling-validity/traceability.json](../specs/004-scheduling-validity/traceability.json) | sdd_contract |
| [specs/005-postprocess-integrity/evidence.md](../specs/005-postprocess-integrity/evidence.md) | sdd_contract |
| [specs/005-postprocess-integrity/plan.md](../specs/005-postprocess-integrity/plan.md) | sdd_contract |
| [specs/005-postprocess-integrity/spec.md](../specs/005-postprocess-integrity/spec.md) | sdd_contract |
| [specs/005-postprocess-integrity/tasks.md](../specs/005-postprocess-integrity/tasks.md) | sdd_contract |
| [specs/005-postprocess-integrity/traceability.json](../specs/005-postprocess-integrity/traceability.json) | sdd_contract |
| [specs/006-month-continuity/evidence.md](../specs/006-month-continuity/evidence.md) | sdd_contract |
| [specs/006-month-continuity/plan.md](../specs/006-month-continuity/plan.md) | sdd_contract |
| [specs/006-month-continuity/spec.md](../specs/006-month-continuity/spec.md) | sdd_contract |
| [specs/006-month-continuity/tasks.md](../specs/006-month-continuity/tasks.md) | sdd_contract |
| [specs/006-month-continuity/traceability.json](../specs/006-month-continuity/traceability.json) | sdd_contract |
| [specs/007-calendar-shift-model/evidence.md](../specs/007-calendar-shift-model/evidence.md) | sdd_contract |
| [specs/007-calendar-shift-model/plan.md](../specs/007-calendar-shift-model/plan.md) | sdd_contract |
| [specs/007-calendar-shift-model/spec.md](../specs/007-calendar-shift-model/spec.md) | sdd_contract |
| [specs/007-calendar-shift-model/tasks.md](../specs/007-calendar-shift-model/tasks.md) | sdd_contract |
| [specs/007-calendar-shift-model/traceability.json](../specs/007-calendar-shift-model/traceability.json) | sdd_contract |
| [specs/008-workload-quality/evidence.md](../specs/008-workload-quality/evidence.md) | sdd_contract |
| [specs/008-workload-quality/plan.md](../specs/008-workload-quality/plan.md) | sdd_contract |
| [specs/008-workload-quality/spec.md](../specs/008-workload-quality/spec.md) | sdd_contract |
| [specs/008-workload-quality/tasks.md](../specs/008-workload-quality/tasks.md) | sdd_contract |
| [specs/008-workload-quality/traceability.json](../specs/008-workload-quality/traceability.json) | sdd_contract |
| [specs/009-schedule-revisions/evidence.md](../specs/009-schedule-revisions/evidence.md) | sdd_contract |
| [specs/009-schedule-revisions/plan.md](../specs/009-schedule-revisions/plan.md) | sdd_contract |
| [specs/009-schedule-revisions/spec.md](../specs/009-schedule-revisions/spec.md) | sdd_contract |
| [specs/009-schedule-revisions/tasks.md](../specs/009-schedule-revisions/tasks.md) | sdd_contract |
| [specs/009-schedule-revisions/traceability.json](../specs/009-schedule-revisions/traceability.json) | sdd_contract |
| [specs/010-ui-configuration/evidence.md](../specs/010-ui-configuration/evidence.md) | sdd_contract |
| [specs/010-ui-configuration/plan.md](../specs/010-ui-configuration/plan.md) | sdd_contract |
| [specs/010-ui-configuration/spec.md](../specs/010-ui-configuration/spec.md) | sdd_contract |
| [specs/010-ui-configuration/tasks.md](../specs/010-ui-configuration/tasks.md) | sdd_contract |
| [specs/010-ui-configuration/traceability.json](../specs/010-ui-configuration/traceability.json) | sdd_contract |
| [specs/011-delivery-assurance/evidence.md](../specs/011-delivery-assurance/evidence.md) | sdd_contract |
| [specs/011-delivery-assurance/plan.md](../specs/011-delivery-assurance/plan.md) | sdd_contract |
| [specs/011-delivery-assurance/spec.md](../specs/011-delivery-assurance/spec.md) | sdd_contract |
| [specs/011-delivery-assurance/tasks.md](../specs/011-delivery-assurance/tasks.md) | sdd_contract |
| [specs/011-delivery-assurance/traceability.json](../specs/011-delivery-assurance/traceability.json) | sdd_contract |
| [specs/012-project-audit/audit.md](../specs/012-project-audit/audit.md) | sdd_contract |
| [specs/012-project-audit/evidence.md](../specs/012-project-audit/evidence.md) | sdd_contract |
| [specs/012-project-audit/github-protection.json](../specs/012-project-audit/github-protection.json) | sdd_contract |
| [specs/012-project-audit/plan.md](../specs/012-project-audit/plan.md) | sdd_contract |
| [specs/012-project-audit/spec.md](../specs/012-project-audit/spec.md) | sdd_contract |
| [specs/012-project-audit/tasks.md](../specs/012-project-audit/tasks.md) | sdd_contract |
| [specs/012-project-audit/traceability.json](../specs/012-project-audit/traceability.json) | sdd_contract |
| [specs/013-product-logic-audit/audit.md](../specs/013-product-logic-audit/audit.md) | sdd_contract |
| [specs/013-product-logic-audit/evidence.md](../specs/013-product-logic-audit/evidence.md) | sdd_contract |
| [specs/013-product-logic-audit/plan.md](../specs/013-product-logic-audit/plan.md) | sdd_contract |
| [specs/013-product-logic-audit/spec.md](../specs/013-product-logic-audit/spec.md) | sdd_contract |
| [specs/013-product-logic-audit/tasks.md](../specs/013-product-logic-audit/tasks.md) | sdd_contract |
| [specs/013-product-logic-audit/traceability.json](../specs/013-product-logic-audit/traceability.json) | sdd_contract |
| [specs/014-product-reliability/evidence.md](../specs/014-product-reliability/evidence.md) | sdd_contract |
| [specs/014-product-reliability/plan.md](../specs/014-product-reliability/plan.md) | sdd_contract |
| [specs/014-product-reliability/spec.md](../specs/014-product-reliability/spec.md) | sdd_contract |
| [specs/014-product-reliability/tasks.md](../specs/014-product-reliability/tasks.md) | sdd_contract |
| [specs/014-product-reliability/traceability.json](../specs/014-product-reliability/traceability.json) | sdd_contract |
| [specs/015-guided-authoring/evidence.md](../specs/015-guided-authoring/evidence.md) | sdd_contract |
| [specs/015-guided-authoring/plan.md](../specs/015-guided-authoring/plan.md) | sdd_contract |
| [specs/015-guided-authoring/spec.md](../specs/015-guided-authoring/spec.md) | sdd_contract |
| [specs/015-guided-authoring/tasks.md](../specs/015-guided-authoring/tasks.md) | sdd_contract |
| [specs/015-guided-authoring/traceability.json](../specs/015-guided-authoring/traceability.json) | sdd_contract |
| [specs/016-stable-replanning/evidence.md](../specs/016-stable-replanning/evidence.md) | sdd_contract |
| [specs/016-stable-replanning/plan.md](../specs/016-stable-replanning/plan.md) | sdd_contract |
| [specs/016-stable-replanning/spec.md](../specs/016-stable-replanning/spec.md) | sdd_contract |
| [specs/016-stable-replanning/tasks.md](../specs/016-stable-replanning/tasks.md) | sdd_contract |
| [specs/016-stable-replanning/traceability.json](../specs/016-stable-replanning/traceability.json) | sdd_contract |
| [specs/017-two-month-quality/evidence.md](../specs/017-two-month-quality/evidence.md) | sdd_contract |
| [specs/017-two-month-quality/plan.md](../specs/017-two-month-quality/plan.md) | sdd_contract |
| [specs/017-two-month-quality/spec.md](../specs/017-two-month-quality/spec.md) | sdd_contract |
| [specs/017-two-month-quality/tasks.md](../specs/017-two-month-quality/tasks.md) | sdd_contract |
| [specs/017-two-month-quality/traceability.json](../specs/017-two-month-quality/traceability.json) | sdd_contract |
| [specs/018-personnel-onboarding/analysis.md](../specs/018-personnel-onboarding/analysis.md) | sdd_contract |
| [specs/018-personnel-onboarding/evidence.md](../specs/018-personnel-onboarding/evidence.md) | sdd_contract |
| [specs/018-personnel-onboarding/plan.md](../specs/018-personnel-onboarding/plan.md) | sdd_contract |
| [specs/018-personnel-onboarding/spec.md](../specs/018-personnel-onboarding/spec.md) | sdd_contract |
| [specs/018-personnel-onboarding/tasks.md](../specs/018-personnel-onboarding/tasks.md) | sdd_contract |
| [specs/018-personnel-onboarding/traceability.json](../specs/018-personnel-onboarding/traceability.json) | sdd_contract |
| [specs/019-smooth-authoring/analysis.md](../specs/019-smooth-authoring/analysis.md) | sdd_contract |
| [specs/019-smooth-authoring/evidence.md](../specs/019-smooth-authoring/evidence.md) | sdd_contract |
| [specs/019-smooth-authoring/plan.md](../specs/019-smooth-authoring/plan.md) | sdd_contract |
| [specs/019-smooth-authoring/spec.md](../specs/019-smooth-authoring/spec.md) | sdd_contract |
| [specs/019-smooth-authoring/tasks.md](../specs/019-smooth-authoring/tasks.md) | sdd_contract |
| [specs/019-smooth-authoring/traceability.json](../specs/019-smooth-authoring/traceability.json) | sdd_contract |
| [src/duty_schedule/__init__.py](../src/duty_schedule/__init__.py) | domain |
| [src/duty_schedule/_errors_fmt.py](../src/duty_schedule/_errors_fmt.py) | domain |
| [src/duty_schedule/api/__init__.py](../src/duty_schedule/api/__init__.py) | api |
| [src/duty_schedule/api/auth.py](../src/duty_schedule/api/auth.py) | api |
| [src/duty_schedule/api/errors.py](../src/duty_schedule/api/errors.py) | api |
| [src/duty_schedule/api/planning.py](../src/duty_schedule/api/planning.py) | api |
| [src/duty_schedule/api/ratelimit.py](../src/duty_schedule/api/ratelimit.py) | api |
| [src/duty_schedule/api/routes/__init__.py](../src/duty_schedule/api/routes/__init__.py) | api |
| [src/duty_schedule/api/routes/config.py](../src/duty_schedule/api/routes/config.py) | api |
| [src/duty_schedule/api/routes/export.py](../src/duty_schedule/api/routes/export.py) | api |
| [src/duty_schedule/api/routes/holidays.py](../src/duty_schedule/api/routes/holidays.py) | api |
| [src/duty_schedule/api/routes/schedule.py](../src/duty_schedule/api/routes/schedule.py) | api |
| [src/duty_schedule/api/routes/whatif.py](../src/duty_schedule/api/routes/whatif.py) | api |
| [src/duty_schedule/api/schemas.py](../src/duty_schedule/api/schemas.py) | api |
| [src/duty_schedule/api/settings.py](../src/duty_schedule/api/settings.py) | api |
| [src/duty_schedule/api/whatif_service.py](../src/duty_schedule/api/whatif_service.py) | api |
| [src/duty_schedule/calendar.py](../src/duty_schedule/calendar.py) | domain |
| [src/duty_schedule/cli.py](../src/duty_schedule/cli.py) | domain |
| [src/duty_schedule/constants.py](../src/duty_schedule/constants.py) | domain |
| [src/duty_schedule/costs.py](../src/duty_schedule/costs.py) | domain |
| [src/duty_schedule/export/__init__.py](../src/duty_schedule/export/__init__.py) | export |
| [src/duty_schedule/export/filenames.py](../src/duty_schedule/export/filenames.py) | export |
| [src/duty_schedule/export/ics.py](../src/duty_schedule/export/ics.py) | export |
| [src/duty_schedule/export/pdf.py](../src/duty_schedule/export/pdf.py) | export |
| [src/duty_schedule/export/xls.py](../src/duty_schedule/export/xls.py) | export |
| [src/duty_schedule/input_validation.py](../src/duty_schedule/input_validation.py) | domain |
| [src/duty_schedule/logging.py](../src/duty_schedule/logging.py) | domain |
| [src/duty_schedule/models.py](../src/duty_schedule/models.py) | domain |
| [src/duty_schedule/project.py](../src/duty_schedule/project.py) | domain |
| [src/duty_schedule/quality_history.py](../src/duty_schedule/quality_history.py) | domain |
| [src/duty_schedule/scheduler/__init__.py](../src/duty_schedule/scheduler/__init__.py) | scheduler |
| [src/duty_schedule/scheduler/changelog.py](../src/duty_schedule/scheduler/changelog.py) | scheduler |
| [src/duty_schedule/scheduler/constraints.py](../src/duty_schedule/scheduler/constraints.py) | scheduler |
| [src/duty_schedule/scheduler/core.py](../src/duty_schedule/scheduler/core.py) | scheduler |
| [src/duty_schedule/scheduler/greedy.py](../src/duty_schedule/scheduler/greedy.py) | scheduler |
| [src/duty_schedule/scheduler/multimonth.py](../src/duty_schedule/scheduler/multimonth.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/__init__.py](../src/duty_schedule/scheduler/postprocess/__init__.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/balance.py](../src/duty_schedule/scheduler/postprocess/balance.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/carry_over_calc.py](../src/duty_schedule/scheduler/postprocess/carry_over_calc.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/helpers.py](../src/duty_schedule/scheduler/postprocess/helpers.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/isolation.py](../src/duty_schedule/scheduler/postprocess/isolation.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/metrics.py](../src/duty_schedule/scheduler/postprocess/metrics.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/pipeline.py](../src/duty_schedule/scheduler/postprocess/pipeline.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/quality.py](../src/duty_schedule/scheduler/postprocess/quality.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/target.py](../src/duty_schedule/scheduler/postprocess/target.py) | scheduler |
| [src/duty_schedule/scheduler/postprocess/validation.py](../src/duty_schedule/scheduler/postprocess/validation.py) | scheduler |
| [src/duty_schedule/scheduler/rules.py](../src/duty_schedule/scheduler/rules.py) | scheduler |
| [src/duty_schedule/scheduler/solver.py](../src/duty_schedule/scheduler/solver.py) | scheduler |
| [src/duty_schedule/scheduler/validation.py](../src/duty_schedule/scheduler/validation.py) | scheduler |
| [src/duty_schedule/stats.py](../src/duty_schedule/stats.py) | domain |
| [src/duty_schedule/ui/__init__.py](../src/duty_schedule/ui/__init__.py) | ui |
| [src/duty_schedule/ui/autosave.py](../src/duty_schedule/ui/autosave.py) | ui |
| [src/duty_schedule/ui/autosave_component/index.html](../src/duty_schedule/ui/autosave_component/index.html) | ui |
| [src/duty_schedule/ui/builders.py](../src/duty_schedule/ui/builders.py) | ui |
| [src/duty_schedule/ui/components.py](../src/duty_schedule/ui/components.py) | ui |
| [src/duty_schedule/ui/config_io.py](../src/duty_schedule/ui/config_io.py) | ui |
| [src/duty_schedule/ui/mappings.py](../src/duty_schedule/ui/mappings.py) | ui |
| [src/duty_schedule/ui/onboarding.py](../src/duty_schedule/ui/onboarding.py) | ui |
| [src/duty_schedule/ui/state.py](../src/duty_schedule/ui/state.py) | ui |
| [src/duty_schedule/ui/views.py](../src/duty_schedule/ui/views.py) | ui |
| [src/duty_schedule/validation.py](../src/duty_schedule/validation.py) | domain |
| [src/duty_schedule/workload.py](../src/duty_schedule/workload.py) | domain |
| [src/duty_schedule/xls_import.py](../src/duty_schedule/xls_import.py) | domain |
| [tests/__init__.py](../tests/__init__.py) | tests |
| [tests/conftest.py](../tests/conftest.py) | tests |
| [tests/contract/__init__.py](../tests/contract/__init__.py) | tests |
| [tests/contract/conftest.py](../tests/contract/conftest.py) | tests |
| [tests/contract/test_api_auth_contract.py](../tests/contract/test_api_auth_contract.py) | tests |
| [tests/contract/test_api_content_type_contract.py](../tests/contract/test_api_content_type_contract.py) | tests |
| [tests/contract/test_api_contract.py](../tests/contract/test_api_contract.py) | tests |
| [tests/contract/test_api_error_contract.py](../tests/contract/test_api_error_contract.py) | tests |
| [tests/contract/test_api_ratelimit_contract.py](../tests/contract/test_api_ratelimit_contract.py) | tests |
| [tests/contract/test_api_response_schema_contract.py](../tests/contract/test_api_response_schema_contract.py) | tests |
| [tests/contract/test_api_strict_validation.py](../tests/contract/test_api_strict_validation.py) | tests |
| [tests/contract/test_config_yaml_contract.py](../tests/contract/test_config_yaml_contract.py) | tests |
| [tests/contract/test_export_format_contract.py](../tests/contract/test_export_format_contract.py) | tests |
| [tests/contract/test_model_contracts.py](../tests/contract/test_model_contracts.py) | tests |
| [tests/contract/test_openapi_snapshot.py](../tests/contract/test_openapi_snapshot.py) | tests |
| [tests/contract/test_product_inputs.py](../tests/contract/test_product_inputs.py) | tests |
| [tests/contract/test_quality_context.py](../tests/contract/test_quality_context.py) | tests |
| [tests/contract/test_revision_api.py](../tests/contract/test_revision_api.py) | tests |
| [tests/e2e/__init__.py](../tests/e2e/__init__.py) | tests |
| [tests/e2e/conftest.py](../tests/e2e/conftest.py) | tests |
| [tests/e2e/test_cli_workflow.py](../tests/e2e/test_cli_workflow.py) | tests |
| [tests/e2e/test_streamlit_api.py](../tests/e2e/test_streamlit_api.py) | tests |
| [tests/integration/__init__.py](../tests/integration/__init__.py) | tests |
| [tests/integration/test_api_auth_integration.py](../tests/integration/test_api_auth_integration.py) | tests |
| [tests/integration/test_api_endpoints.py](../tests/integration/test_api_endpoints.py) | tests |
| [tests/integration/test_carry_over.py](../tests/integration/test_carry_over.py) | tests |
| [tests/integration/test_edge_cases.py](../tests/integration/test_edge_cases.py) | tests |
| [tests/integration/test_full_schedule.py](../tests/integration/test_full_schedule.py) | tests |
| [tests/integration/test_hypothesis.py](../tests/integration/test_hypothesis.py) | tests |
| [tests/integration/test_logging_integration.py](../tests/integration/test_logging_integration.py) | tests |
| [tests/integration/test_multimonth.py](../tests/integration/test_multimonth.py) | tests |
| [tests/integration/test_new_features.py](../tests/integration/test_new_features.py) | tests |
| [tests/integration/test_pins.py](../tests/integration/test_pins.py) | tests |
| [tests/integration/test_pipeline_hour_compatibility.py](../tests/integration/test_pipeline_hour_compatibility.py) | tests |
| [tests/integration/test_priority_integration.py](../tests/integration/test_priority_integration.py) | tests |
| [tests/integration/test_randomized_schedules.py](../tests/integration/test_randomized_schedules.py) | tests |
| [tests/integration/test_replanning.py](../tests/integration/test_replanning.py) | tests |
| [tests/integration/test_two_month_quality.py](../tests/integration/test_two_month_quality.py) | tests |
| [tests/integration/test_whatif_endpoint.py](../tests/integration/test_whatif_endpoint.py) | tests |
| [tests/integration/test_xls_roundtrip.py](../tests/integration/test_xls_roundtrip.py) | tests |
| [tests/performance/__init__.py](../tests/performance/__init__.py) | tests |
| [tests/performance/test_large_team.py](../tests/performance/test_large_team.py) | tests |
| [tests/performance/test_scheduler_benchmark.py](../tests/performance/test_scheduler_benchmark.py) | tests |
| [tests/system/__init__.py](../tests/system/__init__.py) | tests |
| [tests/system/test_business_rules.py](../tests/system/test_business_rules.py) | tests |
| [tests/system/test_constraint_satisfaction.py](../tests/system/test_constraint_satisfaction.py) | tests |
| [tests/system/test_determinism.py](../tests/system/test_determinism.py) | tests |
| [tests/ui/__init__.py](../tests/ui/__init__.py) | tests |
| [tests/ui/conftest.py](../tests/ui/conftest.py) | tests |
| [tests/ui/fixtures.py](../tests/ui/fixtures.py) | tests |
| [tests/ui/test_export_download.py](../tests/ui/test_export_download.py) | tests |
| [tests/ui/test_first_month_journey.py](../tests/ui/test_first_month_journey.py) | tests |
| [tests/ui/test_page_load.py](../tests/ui/test_page_load.py) | tests |
| [tests/ui/test_personnel_onboarding.py](../tests/ui/test_personnel_onboarding.py) | tests |
| [tests/ui/test_product_recovery.py](../tests/ui/test_product_recovery.py) | tests |
| [tests/ui/test_project_journey.py](../tests/ui/test_project_journey.py) | tests |
| [tests/ui/test_quality_journey.py](../tests/ui/test_quality_journey.py) | tests |
| [tests/ui/test_replanning_journey.py](../tests/ui/test_replanning_journey.py) | tests |
| [tests/ui/test_schedule_generation.py](../tests/ui/test_schedule_generation.py) | tests |
| [tests/ui/test_smooth_authoring.py](../tests/ui/test_smooth_authoring.py) | tests |
| [tests/unit/__init__.py](../tests/unit/__init__.py) | tests |
| [tests/unit/test_api_auth.py](../tests/unit/test_api_auth.py) | tests |
| [tests/unit/test_api_errors.py](../tests/unit/test_api_errors.py) | tests |
| [tests/unit/test_api_ratelimit.py](../tests/unit/test_api_ratelimit.py) | tests |
| [tests/unit/test_api_schemas.py](../tests/unit/test_api_schemas.py) | tests |
| [tests/unit/test_api_settings.py](../tests/unit/test_api_settings.py) | tests |
| [tests/unit/test_calendar.py](../tests/unit/test_calendar.py) | tests |
| [tests/unit/test_calendar_model.py](../tests/unit/test_calendar_model.py) | tests |
| [tests/unit/test_carry_over_calc.py](../tests/unit/test_carry_over_calc.py) | tests |
| [tests/unit/test_changelog.py](../tests/unit/test_changelog.py) | tests |
| [tests/unit/test_cli.py](../tests/unit/test_cli.py) | tests |
| [tests/unit/test_cli_exception_handling.py](../tests/unit/test_cli_exception_handling.py) | tests |
| [tests/unit/test_cli_project.py](../tests/unit/test_cli_project.py) | tests |
| [tests/unit/test_constraints.py](../tests/unit/test_constraints.py) | tests |
| [tests/unit/test_costs.py](../tests/unit/test_costs.py) | tests |
| [tests/unit/test_delivery_workflows.py](../tests/unit/test_delivery_workflows.py) | tests |
| [tests/unit/test_equalize_cross_city.py](../tests/unit/test_equalize_cross_city.py) | tests |
| [tests/unit/test_export_security.py](../tests/unit/test_export_security.py) | tests |
| [tests/unit/test_export_time_model.py](../tests/unit/test_export_time_model.py) | tests |
| [tests/unit/test_failure_modes.py](../tests/unit/test_failure_modes.py) | tests |
| [tests/unit/test_history.py](../tests/unit/test_history.py) | tests |
| [tests/unit/test_hour_consumers.py](../tests/unit/test_hour_consumers.py) | tests |
| [tests/unit/test_ics_per_employee.py](../tests/unit/test_ics_per_employee.py) | tests |
| [tests/unit/test_logging_features.py](../tests/unit/test_logging_features.py) | tests |
| [tests/unit/test_logging_setup.py](../tests/unit/test_logging_setup.py) | tests |
| [tests/unit/test_max_consecutive_constants.py](../tests/unit/test_max_consecutive_constants.py) | tests |
| [tests/unit/test_metrics.py](../tests/unit/test_metrics.py) | tests |
| [tests/unit/test_models.py](../tests/unit/test_models.py) | tests |
| [tests/unit/test_multimonth.py](../tests/unit/test_multimonth.py) | tests |
| [tests/unit/test_pdf_export.py](../tests/unit/test_pdf_export.py) | tests |
| [tests/unit/test_personnel_onboarding.py](../tests/unit/test_personnel_onboarding.py) | tests |
| [tests/unit/test_pipeline.py](../tests/unit/test_pipeline.py) | tests |
| [tests/unit/test_pipeline_integrity.py](../tests/unit/test_pipeline_integrity.py) | tests |
| [tests/unit/test_planning_rules.py](../tests/unit/test_planning_rules.py) | tests |
| [tests/unit/test_postprocess.py](../tests/unit/test_postprocess.py) | tests |
| [tests/unit/test_postprocess_priority.py](../tests/unit/test_postprocess_priority.py) | tests |
| [tests/unit/test_product_integrity.py](../tests/unit/test_product_integrity.py) | tests |
| [tests/unit/test_project.py](../tests/unit/test_project.py) | tests |
| [tests/unit/test_project_context.py](../tests/unit/test_project_context.py) | tests |
| [tests/unit/test_replanning.py](../tests/unit/test_replanning.py) | tests |
| [tests/unit/test_schedule_diff.py](../tests/unit/test_schedule_diff.py) | tests |
| [tests/unit/test_scheduler.py](../tests/unit/test_scheduler.py) | tests |
| [tests/unit/test_sdd.py](../tests/unit/test_sdd.py) | tests |
| [tests/unit/test_search_outcomes.py](../tests/unit/test_search_outcomes.py) | tests |
| [tests/unit/test_solver.py](../tests/unit/test_solver.py) | tests |
| [tests/unit/test_stats.py](../tests/unit/test_stats.py) | tests |
| [tests/unit/test_two_month_quality.py](../tests/unit/test_two_month_quality.py) | tests |
| [tests/unit/test_ui_autosave.py](../tests/unit/test_ui_autosave.py) | tests |
| [tests/unit/test_ui_validation.py](../tests/unit/test_ui_validation.py) | tests |
| [tests/unit/test_ui_workflow.py](../tests/unit/test_ui_workflow.py) | tests |
| [tests/unit/test_validation.py](../tests/unit/test_validation.py) | tests |
| [tests/unit/test_validation_postprocess.py](../tests/unit/test_validation_postprocess.py) | tests |
| [tests/unit/test_whatif_service.py](../tests/unit/test_whatif_service.py) | tests |
| [tests/unit/test_workload.py](../tests/unit/test_workload.py) | tests |
| [tests/unit/test_xls_import.py](../tests/unit/test_xls_import.py) | tests |
| [uv.lock](../uv.lock) | project |

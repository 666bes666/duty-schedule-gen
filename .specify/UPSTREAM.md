# Spec Kit provenance and local adaptations

Scaffold: official `specify-cli==1.1.3` (MIT), generated on 2026-10-10 using
`uvx --from specify-cli==1.1.3 specify init --here --integration codex --script sh
--ignore-agent-tools --non-interactive`, then `specify integration install claude`.
Source: https://github.com/github/spec-kit/releases/tag/v1.1.3.

Initialization ran in a temporary directory. Only shared infrastructure and
Codex/Claude integration files were copied into this repository. No `git`
extension is installed. The bundled Bash scripts remain unmodified.

Local adaptations:

- Project-specific constitution and AGENTS instructions.
- Spec/plan templates identify the feature directory separately from `dev`.
- Tasks template requires tests for behavior changes, consistent with project rules.
- Added traceability/evidence templates and a stdlib validator with CI/pre-commit.
- Specify skills honor `SPECIFY_FEATURE_NO_PERSIST` in their path-persistence step.
- Bundled workflow uses analysis and convergence instead of extra human approval
  gates. If convergence finds unfinished tasks, continue implementation and checks.

Integration manifests contain upstream hashes. Locally modified templates/skills
therefore intentionally differ. Before upgrading, review the pinned release in a
temporary directory, compare the generated diff, and reapply local adaptations.
Do not run `init --force` or `integration upgrade --force` over local customizations
without reviewing what will be replaced. No global CLI installation is required;
use `uvx --from specify-cli==1.1.3 specify ...` for management commands.

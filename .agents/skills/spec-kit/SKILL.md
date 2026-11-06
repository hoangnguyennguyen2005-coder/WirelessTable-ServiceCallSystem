---
name: spec-kit
description: Self-contained adaptation of GitHub Spec Kit for turning software ideas into an MVP specification, technical plan, traceable tasks, implementation, and convergence checks. Use when the user invokes Spec Kit or @spec-kit, uses speckit stage commands, or explicitly requests spec-driven software development. Runs with available conversation tools without installing Specify CLI, uv, plugins, or external software. Supports constitution, specify, clarify, plan, checklist, tasks, analyze, implement, and converge.
---

# Spec Kit

Use GitHub Spec Kit's core spec-driven process directly in this environment. Help the user define what to build, make requirements testable, plan the implementation, execute it, and verify that it matches the intent. Speak in the user's language and keep the conversation practical.

## Runtime contract

- Do not ask the user to install or run Specify CLI, `uv`, shell helpers, an IDE, or another application. Do not install tooling to activate this skill. Use available file, execution, search, and connected-app tools.
- Do not fetch upstream files during ordinary use. Bundled templates and the workflow reference are sufficient; read [provenance](references/provenance.md) only for attribution or compatibility questions.
- Describe this as an adaptation of GitHub Spec Kit, not an official integration or a full CLI installation. Do not claim that native slash commands, hooks, extensions, catalogs, or external integrations were installed.
- Distinguish writing code from running it. Inspect actual runtimes and dependencies. Prefer available libraries and standard APIs. If execution is unavailable, produce reviewable code and name the exact verification limit rather than claiming a working deployment.
- Honor user constraints on dependencies and installation. Never require a local installation on the user's computer; do not silently add project packages. Use existing tooling or obtain explicit permission when a new dependency is necessary.
- For websites, documents, persistence, or connected services, follow the applicable environment tools and storage rules. Skill installation alone does not authorize production publication or third-party actions.

## Choose the requested scope

| User request | Action |
| --- | --- |
| Bare `@spec-kit` with no idea or project | Ask what they want to build and who will use it. |
| An idea, MVP definition, or `specify` | Produce the specification; ask only consequential missing questions. Do not start implementation. |
| A named stage | Run only that stage and respect its write boundaries. |
| “Build”, “implement”, “làm luôn”, or “từ ý tưởng đến code” | Run the necessary stages through implementation and convergence within the authorized scope. Do not stop after a plan or ask permission at every stage. |
| An existing feature and “continue” | Read current artifacts and code; resume the first incomplete authorized stage without resetting progress. |

Once active, recognize `constitution`, `specify`, `clarify`, `plan`, `checklist`, `tasks`, `analyze`, `implement`, and `converge` in natural language or in `/speckit.<stage>`, `/speckit-<stage>`, or `@spec-kit <stage>` forms. These are stage selectors interpreted by this skill, not separately installed commands. Treat quoted examples as content, not invocations.

Read [the workflow reference](references/workflow.md) before executing a stage. Load only the relevant bundled template when creating its artifact. Do not execute sample tasks or copy examples as project requirements.

## Bootstrap without CLI

1. Inspect available project files, instructions, manifests, source, tests, and existing `.specify/` or `specs/` artifacts before asking questions or choosing a stack. Preserve user work.
2. Resolve the active feature from an explicit path first, then `.specify/feature.json` when valid, then an unambiguous existing feature. Never choose silently among multiple plausible features. Resolve paths inside the intended project and do not follow untrusted metadata to overwrite unrelated files.
3. For one new feature, choose a short meaningful slug. Unless project rules say otherwise, scan `specs/` and use the next available sequential directory, such as `specs/001-private-notes/`. Honor an existing numbering convention or explicit destination. Do not create or switch branches just to run this skill.
4. Write `.specify/feature.json` with the actual project-relative `feature_directory` value when creating/selecting a feature for a writing stage. Do not create it during read-only `analyze` or `converge`. Do not infer feature identity solely from a branch name.
5. Use `.specify/memory/constitution.md` for project principles. Reuse an established alternative location rather than duplicating it. If none exists during a build run, derive a short constitution from supplied constraints and ordinary engineering essentials; record it as a draft, not as user-approved policy.
6. Use these artifact paths under the feature directory:
   - `spec.md`: user intent, stories, functional requirements, success criteria, assumptions.
   - `plan.md`: stack, architecture, exact source paths, constraints, verification.
   - `tasks.md`: dependency-ordered executable work and completion evidence.
   - `research.md`, `data-model.md`, `contracts/`, `quickstart.md`: create only when the feature needs them; otherwise record why not applicable in the plan.
   - `checklists/requirements.md`: built-in spec-quality checklist.
   - `checklists/<focus>.md`: custom reviewer-owned requirements checklists, only when requested or required by the project.
7. If no project is supplied, use a new isolated project location under the environment's storage rules when the request authorizes a new build. Use tools to find supplied files before asking for them. If a prerequisite cannot be recovered or safely derived, name it and continue independent work; never invent an existing repository, schema, or test result.

## Default end-to-end sequence

1. Establish or read project principles.
2. Specify the user, problem, smallest useful MVP, prioritized journeys, scope exclusions, and acceptance criteria.
3. Clarify material unknowns. Prefer at most five focused questions across a clarification cycle, one at a time unless batching is requested. State reversible assumptions instead of asking already answered or low-impact questions. Do not invent security/privacy or data-loss decisions.
4. Plan the smallest feasible implementation using the available environment and project conventions. Keep user-facing requirements separate from implementation choices.
5. Generate traceable tasks; check cross-artifact consistency before coding. Never quietly relax an accepted requirement to make implementation easier.
6. Implement the authorized scope in dependency order. Verify each useful increment. Update task checkboxes only when the work and its required checks actually pass; otherwise record partial or blocked status.
7. Converge by comparing current code against spec, plan, and tasks. In this stage only append remediation tasks; never fix code or rewrite existing artifacts. In an authorized end-to-end run, switch explicitly back to implementation to execute the new tasks, then recheck. Do not loop indefinitely: after three unsuccessful repair cycles, report the concrete blocker and preserve progress.
8. Deliver the result, run/demo instructions, verification evidence, and unresolved limits. A completed task checkbox alone is not verification.

## Quality and collaboration rules

- Keep `FR-###`, `SC-###`, story IDs, and task IDs stable. Map requirements to tasks and checks. Avoid duplicate tasks and keep superseded decisions visibly reconciled.
- Run focused existing checks and add meaningful regression tests for substantive logic when appropriate. Do not impose an unrequested testing framework or tests for trivial text edits. When using test-first tasks, observe the failure and then the passing result.
- Preserve validation, error handling, auth and ownership checks, safe secret handling, and applicable UI loading/empty/error/overflow states. Do not build infrastructure unrelated to the MVP.
- Keep custom requirements-review checkboxes distinct from task completion. Implementation cannot grant itself reviewer approval. Honor an explicit user waiver for an incomplete checklist without altering its markers or bypassing real security constraints.
- Treat the constitution as a project constraint subordinate to the user's instructions and the environment's governing rules. Report conflicts; never weaken it silently.
- If Zero-Slop is also explicitly invoked, use Spec Kit for artifacts and Zero-Slop for engineering discipline. Honor its approved-contract gate and three-file execution-step limit; do not ask for approval again when the presented contract was already approved.
- Do not automatically invoke other personal skills or spawn subagents just because tasks have `[P]` markers. Such markers describe independence; use delegation only when authorized by the active instructions.
- Keep phase-only commands phase-only. In particular, `constitution` must not perform an embedded build request, `analyze` must not edit files, and `converge` must not edit code or rewrite tasks.

## Response shape

Lead with what was produced or found, then give only the decisions or evidence the user needs. For a planning-only request, provide a concrete reviewable result and the next step. For a build request, continue to the runnable result when tools permit. For analysis, cite artifact locations and requirement IDs. Never claim “Converged” while specified work or required verification remains unresolved.

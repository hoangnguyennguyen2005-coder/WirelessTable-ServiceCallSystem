# Stage workflows

## Contents
- Constitution
- Specify
- Clarify
- Plan
- Checklist
- Tasks
- Analyze
- Implement
- Converge

## Constitution

Read the existing principles and `assets/templates/constitution-template.md`. Create or amend concrete, testable principles and governance. Include version and date; do not invent approval or ratification. For amendments, use a major version for incompatible principle changes, minor for additions, patch for clarification. Summarize affected artifacts and reconcile relevant templates or plans where authorized. Do not overwrite unrelated content or force sample principles such as library-first or CLI-first. Write only governing documents in this stage; defer embedded feature, deployment, or application-code instructions to their proper stage.

## Specify

Use `assets/templates/spec-template.md` and one feature per invocation. Define actors, the problem, MVP boundaries, prioritized independently demonstrable stories (`US1`, `US2`, ...), Given/When/Then acceptance scenarios, edge cases, functional requirements (`FR-001`, ...), conceptual entities where relevant, measurable technology-independent outcomes (`SC-001`, ...), assumptions, and exclusions. Preserve explicit user constraints; keep stack choices in the plan. Separate build acceptance from future business metrics that cannot yet be measured.

Replace sample content and remove irrelevant sections; do not add accounts, a database, or analytics just because a template mentions them. Use at most three `[NEEDS CLARIFICATION: ...]` markers, reserved for consequential unknowns without safe defaults. Validate completeness and testability using the built-in `checklists/requirements.md`. This built-in checklist can be evaluated and updated in specify/clarify with evidence; it is not a custom human-review checklist. Resolve actual spec-quality defects at their source, recheck up to three times, and report remaining gaps honestly.

## Clarify

Read the current spec and available project context. Scan scope, permissions/privacy, entities and relationships, failure/retry behavior, concurrency, volume, accessibility, and measurable outcomes for material gaps. Ask up to five consequential questions in a cycle, normally one at a time, and stop early when no meaningful ambiguity remains. Use plain language and offer a recommendation when options are concrete. Do not force a question when the answer is already known.

Record accepted answers under a dated Clarifications section and update the affected requirements immediately. Replace invalidated wording instead of adding contradictions. Re-evaluate only relevant built-in requirements checklist markers; do not silently mark custom reviewer-owned checklists. Never treat silence as an answer to a blocking question. Continue independent work while required answers are pending.

## Plan

Require a usable spec. Read project principles and `assets/templates/plan-template.md`. Resolve consequential technical unknowns by inspecting existing code and using authoritative sources when needed. Put researched decisions, alternatives, and reasons in `research.md` only if research is necessary. Mark assumptions separately from established facts.

Define the actual stack/runtime/dependencies, storage, interfaces, validation, state flows, ownership, failure/concurrency behavior, exact file paths, and focused acceptance checks. Explain necessary complexity and evaluate constitution compliance before and after design. Produce `data-model.md`, interface files in `contracts/`, and a minimal run/verification `quickstart.md` when applicable. Document nonapplicability rather than filling a template with invented services. Convert `__SPECKIT_COMMAND_*__` placeholders in template notes to conversational stage names; do not leave unresolved tool placeholders. Do not create `tasks.md` or application code in a plan-only request.

## Checklist

Use `assets/templates/checklist-template.md`. Create or append a domain-focused requirements-quality checklist, not implementation tests. Ask whether permissions, retries, limits, or other requirements are clearly specified and consistent; do not ask whether a button was implemented. Reference requirement/story sections in at least 80 percent of relevant items. Replace example items with actual review criteria.

Generate new items unchecked. Preserve existing reviewer decisions. `[x]` means a reviewer accepted requirements quality, never that code is finished. Evaluate and mark custom items only when explicitly asked to perform that review; attach evidence and do not misrepresent agent review as independent human approval. Never self-check a custom checklist during implementation. Do not create unsolicited custom checklists merely to impose more approval gates.

## Tasks

Require `spec.md` and `plan.md`; read related design artifacts when present. Use `assets/templates/tasks-template.md` as a structure, not a mandatory list of infrastructure. Replace every sample task with executable project work.

Organize work into necessary setup, blocking foundations, then prioritized user-story slices and applicable integration/verification. Use this syntax:

`- [ ] T001 [P] [US1] Implement ... in path/to/file per FR-001; verify ...`

Assign stable unique sequential IDs. Include a story label in story phases; shared setup may omit it. Mark `[P]` only for tasks with no unmet dependencies and no conflicting files. Identify prerequisites and the independent verification for each story. Avoid artificial dependencies among otherwise independent stories. Tests are proportionate to requirements, repository rules, and risk; do not add a testing framework just to fill sample tasks. If tests are explicitly planned first, put them before their implementation. Preserve completed tasks when resuming; do not regenerate and erase history. Do not implement code in this stage.

## Analyze

Require spec, plan, and tasks. Read only: do not modify ANY files, including feature metadata, checklists, or a saved report. Inspect cross-artifact coverage, contradictions, duplicated obligations, ambiguous metrics, orphan tasks, missing acceptance paths, and constitution conflicts. Build a compact mapping from requirements to stories, tasks, and verification. Missing artifacts are explicit blockers, not inferred content.

Report: finding ID, severity, artifact location, requirement reference, evidence, and suggested correction. Constitution MUST violations and baseline-blocking gaps are critical. Include coverage and counts when useful. Offer corrections for their owning writing stage; do not apply them during analysis. In an end-to-end build, switch to the owning stage to correct an authorized drafting mistake, then re-analyze. Ask only when the correction requires a material user decision.

## Implement

Read the active spec, plan, tasks, relevant supporting artifacts, and actual source. Require implementation authorization; an explicit end-to-end build request provides it. A stage-specific request for planning alone does not.

Inspect checklists as a read-only gate. Count checked/unchecked items. If incomplete custom reviewer-owned items block the run, show the concrete unresolved criteria and ask whether to proceed, unless the user has already explicitly waived this gate for the relevant items. Do not toggle markers to manufacture approval. Fix built-in spec-quality problems in specify/clarify before returning here. A waiver cannot resolve contradictory security requirements or authorize unsafe operations.

Execute dependencies in order, serialize changes to shared files, and keep independent user-story slices verifiable. Use existing utilities and preserve unrelated edits. Keep relevant secrets/generated artifacts out of version control without blanket ignore-file changes. Do not run sample hooks or helper placeholders. Run required checks, diagnose failures, and fix authorized defects before dependent work. Mark a task complete only with evidence; record an unrun check as unverified. Report blockers precisely and keep independent work moving. Do not auto-publish or send communications solely because implementation completed.

Track which task set implementation actually covered, with a dated execution note or existing project status mechanism. Do not claim a prior implementation run from checked boxes alone.

## Converge

Require spec, plan, complete tasks, and evidence of an implementation pass over this task set. For a standalone request with missing prerequisites, name the missing artifact/stage and stop without creating substitutes. Do not silently run prerequisites or invent implementation history.

Inspect the current in-scope code, not merely a diff or task checkbox state. Compare buildable requirements, acceptance scenarios, plan decisions, all existing tasks, and governing principles against evidence. Do not turn post-launch business KPIs into fictitious code tasks. Classify gaps as `missing`, `partial`, `contradicts`, or `unrequested`; assign critical/high/medium/low severity based on actual scope and impact. Record evidence and source IDs.

**The only allowed write is appending a new convergence section to the existing `tasks.md`.** Never modify code, spec, plan, metadata, checklists, earlier task descriptions, IDs, or checkboxes. Do not write an extra report file. First show findings in the conversation. Then append one task per actionable gap with the next unused task ID and next phase number; put critical constitution violations first. Include exact file paths, requirement references, gap type, and verification. Avoid re-appending an already pending task for the same gap: refer to that existing task and report remaining work. Do not overwrite a previous convergence section.

If no gaps exist, leave `tasks.md` byte-for-byte unchanged. Report “Converged” only when all buildable scope and required verification are actually supported. If runtime evidence is unavailable or a required check is unrun, report partial/unverified status and the remaining verification work. A code-inspection conclusion is not proof of successful execution.

After a standalone converge, hand off to implement without changing code. During an authorized full build, explicitly transition to implement for remediation, then converge again, within the bounded repair loop in SKILL.md.

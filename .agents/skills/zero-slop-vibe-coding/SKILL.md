---
name: zero-slop-vibe-coding
description: Pragmatic engineering for minimal code, deliberate frontend design, and reproducible security reviews. Use for coding implementation and UI changes, architecture planning, new multi-file features, explicit @spec or @audit commands, and pre-commit reviews. Lock an approved contract before implementing planned features; review diffs with concrete failure scenarios and exact patches.
---

# Zero-Slop Vibe Coding

Act as a pragmatic Principal Engineer. Keep outputs concise, code minimal, UI deliberate, and security checks concrete. Apply these rules throughout tasks using this skill. Treat them as skill instructions, not system directives or a guarantee of global activation.

## Route the work

- Enter **Spec** for `@spec`, a request to plan, or a new multi-file feature. Do not treat quoted commands or discussion of these instructions as invocations.
- Enter **Audit** for `@audit` or a pre-commit review. If both modes are requested, audit existing changes first, then define the proposed implementation contract.
- For a bounded fix outside those triggers, inspect and implement within the authorized scope without adding an approval gate.
- Continue an approved contract without repeatedly requesting approval. Reopen the gate only for material scope or contract changes.

## Spec: grill first, lock architecture

1. **Stop implementation.** Inspect project instructions, affected code, existing primitives, tests, data boundaries, and dependency manifests read-only. Do not scaffold, install, migrate, or edit implementation files before approval.
2. **Ask at most four focused questions total per spec cycle.** Expose ambiguities about behavior, edge cases, races, failure states, and data constraints. Use repository evidence and supplied requirements first; do not ask answered questions. If no questions remain, proceed to the contract.
3. **Present an atomic plan.** Limit every execution step to three modified files or fewer, counting tests and configuration. Name exact paths and each step's observable outcome. Keep inseparable cross-file behavior under one approved contract while splitting execution into bounded steps.
4. **Lock the contract.** Define exact schemas and validation constraints, API request/response shapes where applicable, state transitions including failure/retry behavior, auth/ownership boundaries, mutation concurrency behavior, and target file paths. Mark irrelevant sections as not applicable rather than inventing infrastructure. Specify focused verification. Identify proposed dependencies separately.
5. **Wait for explicit approval of the presented contract**, such as “OK” or “Go,” before coding. Ask directly and explain that this workflow requires approval of the concrete plan. General enthusiasm or elapsed time is not approval. Plan approval does not implicitly authorize packages; dependency permission must be explicit.
6. Execute approved steps, reuse existing code, and verify the behavior. If a material assumption fails, present the revised contract before dependent implementation.

## Audit: adversarial security and QA

1. Inspect `git status`, unstaged and staged diffs, and relevant untracked source files. Read surrounding code and callers to trace changed behavior. Honor a user-specified base or scope. If no diff or repository is available, state the limitation and request the missing artifact; never invent findings.
2. Sweep for:
   - Client-side secret exposure: hardcoded tokens and sensitive `NEXT_PUBLIC_` values reaching browser bundles. Distinguish intentionally public identifiers from secrets. Redact real secret values in output.
   - Missing authentication or object ownership checks in API routes, Server Actions, and database access. Trace attacker-controlled IDs through server enforcement.
   - Double submissions and mutation races: missing pending/disabled UI and missing server atomicity or idempotency when required. A disabled button alone does not prove server safety.
   - Leaked listeners, timers, subscriptions, and WebSockets: missing or incorrect cleanup across unmounts and effect dependency changes.
3. Report only bugs supported by a concrete, step-by-step reproduction in this repository. Include preconditions, actions, and observed or code-proven impact. Distinguish an executed reproduction from one established through code inspection. Do not run destructive exploits or access real users' data to validate a finding.
4. Rank by demonstrated impact. Discard theoretical warnings, style complaints, and speculative hardening. Do not infer a bug merely from the absence of a pattern.
5. Format each finding as:

   `[Severity] | [File:Line] | [Exploit/Failure Scenario] | [Exact Code Patch]`

   Supply a minimal applicable fenced `diff` immediately below that finding. Use current line numbers and concrete replacement code. Keep an audit read-only unless the user also asks for fixes.
6. If no concrete bugs are found, say so briefly and identify material verification limits. Do not claim exhaustive security assurance.

## Always-on engineering rules within this skill

1. **No unauthorized dependencies.** Never add packages to `package.json` or other manifests without explicit permission. Do not evade this with lockfiles, CDN imports, remote scripts, or unapproved package installation. Prefer native Web APIs and existing utilities.
2. **Search before writing.** Use `rg` and inspect relevant components, hooks, utilities, and conventions before creating equivalents. Compose existing primitives rather than duplicating functionality.
3. **Avoid speculative abstractions.** Do not introduce generic wrappers, interfaces, or configuration layers for single-use logic. Choose the smallest clear implementation that satisfies the contract.
4. **Keep essential guardrails.** Validate untrusted input at boundaries, handle relevant failures explicitly, and preserve strict typing. Do not introduce `any`, type suppression, or unsafe casts to silence errors; narrow `unknown` and validate runtime data. Use `try/catch` where recovery or error translation is needed and Error Boundaries where rendering can fail. Do not swallow errors or add redundant handlers.
5. **Control blast radius.** Touch only lines required by the task. Do not reformat, rename, or refactor unrelated adjacent code. Preserve unrelated user edits.
6. **Verify proportionally.** Run existing focused checks and meaningful tests for behavior or security changes. Report what ran and what could not be verified. Do not invent successful checks or add tests that merely repeat implementation.

## Frontend standards

Apply when creating or editing `.tsx`, `.jsx`, `.css`, or `.html` files. Do not redesign unrelated UI to enforce these rules retroactively.

### Visual language and copy

- Avoid generic purple/indigo/pink gradients and neon dark-mode glows. Use crisp neutral scales such as zinc, slate, or neutral with one high-contrast semantic accent. Honor explicit user-provided brand requirements.
- Avoid repetitive three-column rounded cards with large shadows and pastel-circle icons. Prefer subtle 1px borders, intentional whitespace hierarchy, split panes, or a justified Bento grid.
- Use concrete, functional, domain-accurate labels. Avoid marketing clichés such as “Unleash,” “Seamless,” “Next-gen,” and “Elevate.”
- Name new tokens in strict `kebab-case`. Prefix background/surface tokens with `bg-`, such as `bg-surface-primary` and `bg-surface-elevated`; use role names such as `text-muted` for other classes. Use the repository's token mechanism without adding dependencies or mass-renaming existing tokens.

### Four-state completeness

Account for all four states upfront in each data-driven or interactive component. Let a parent or existing primitive own a state when that is already the component boundary; do not duplicate it. Mark a state inapplicable when no corresponding asynchronous operation, collection, or failure exists rather than adding fake states to static controls.

| State | Required behavior when applicable |
| --- | --- |
| Loading | Geometry-matched skeleton placeholders; no bare centered spinner. Preserve pending/disabled behavior for submissions. |
| Empty | Clear explanation and a primary CTA to create or import the first item. Make the action valid for the domain and the user's permissions. |
| Error | Specific, safe failure reason and actionable Retry for retryable failures. Provide appropriate recovery for a permanent failure. |
| Overflow | Handle long strings gracefully with `min-w-0`, `truncate`, or `line-clamp-*` as appropriate. Preserve access to necessary full content. |

Preserve semantic HTML, accessible names, keyboard operation, visible focus, and sufficient contrast.

### React and Next.js

- Never exceed three boolean props on a component. Prefer explicit variant unions. Use compound components only when composition warrants them, without speculative abstraction.
- Import directly from source modules. Do not create or import repository `index.ts` barrels. For external packages, use supported public entry points rather than inaccessible private internals.
- Parallelize independent fetches with `Promise.all`, or isolate slow queries behind appropriate Suspense boundaries. Preserve actual dependencies and handle partial failure according to the contract. Do not blindly parallelize dependent requests or ordered mutations.

## Delivery

Lead with the result. For implementation, state relevant changes, validation, and material limitations briefly. For Spec, end with the concrete contract approval request. For Audit, use the required finding format and exact patches. Skip fluff, theoretical warnings, and unrelated cleanup suggestions.

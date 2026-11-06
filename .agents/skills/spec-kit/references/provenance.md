# Upstream provenance and adaptation

- Project: GitHub Spec Kit, https://github.com/github/spec-kit
- Source snapshot: `d64983401db7bed8e49a3839147ed632bc82361e`, retrieved 2026-11-06.
- Methodology reviewed: `README.md`, `templates/commands/{constitution,specify,clarify,plan,checklist,tasks,analyze,implement,converge}.md` at that snapshot.
- Included upstream assets: the five unchanged Markdown templates under `assets/templates/`.
- License: MIT; retain `LICENSE.txt` when distributing these files. Copyright GitHub, Inc.

This is an independent, self-contained adaptation of the core SDD process for the tools available in this conversation. It is not an official GitHub integration or the Specify CLI. It preserves requirements-first specs, prioritized stories, constitution checks, traceable tasks, reviewer-owned custom checklists, read-only analysis, and append-only convergence.

Replace CLI bootstrap, shell helper placeholders, branch hooks, extension execution, and template-layer resolution with direct artifact reading/writing. Do not claim support for installed upstream extensions, presets, catalogs, hooks, agents, or runtime integrations. Do not silently ignore existing project overrides: read the relevant local instructions/templates; when a required installed composition cannot be reproduced, explain the limitation rather than installing a tool or pretending it ran.

Command strings in user messages are conversational stage selectors once this skill is active. They are not new tools or registered native slash commands. No upstream download or external software installation is required during ordinary use; this source snapshot is already bundled.

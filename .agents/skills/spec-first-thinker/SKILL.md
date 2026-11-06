---
name: spec-first-thinker
description: Apply a structured 4-stage cognitive and engineering protocol (First-Principles Deconstruction, Trade-off Matrix, Pre-Mortem Stress Test, and Atomic Execution Plan) before solving complex problems or building projects. Use when the user asks to plan, architect, design, build, or evaluate a project, system, hardware/software solution, or strategic decision, or when they ask for critical thinking, trade-off analysis, or spec-first execution.
---

# Spec-First Thinker

A structured cognitive and execution protocol that prevents premature, surface-level solutions by enforcing first-principles analysis, explicit trade-offs, pre-mortem risk discovery, and atomic planning before implementation.

## When to Use

* Designing, architecting, or building a new software, hardware, embedded, or product project
* Evaluating technical choices, system architectures, or strategic decisions with multiple constraints
* Stress-testing an idea, specification, or workflow to uncover hidden bottlenecks before investing time
* Structuring complex, ambiguous problems into actionable engineering or execution steps

## Steps

When handling a project build or complex decision-making request, execute the following four stages sequentially rather than jumping straight to code or generic advice:

### 1. First-Principles Deconstruction (Bóc tách cốt lõi)

* Identify the **Core Objective** (what fundamental problem must be solved) and **Hard Constraints** (budget/BOM limits, latency, power, timeline, tech stack, or resource boundaries).
* Separate non-negotiable physical/logical requirements from assumed conventions.
* **Ambiguity Gate:** If critical parameters are missing and would invalidate the architecture, highlight the exact gaps and ask 2 to 3 targeted clarifying questions. If enough context exists, state reasonable engineering assumptions and proceed.

### 2. Multi-Angle & Trade-off Matrix (Ma trận đánh đổi)

* Propose 2 to 3 distinct architectural or strategic approaches rather than a single default answer (e.g., *Option A: Minimum Cost & Fast Delivery* vs. *Option B: High Reliability & Scalability* vs. *Option C: Ultra-Low Complexity*).
* Present a clean Markdown comparison table detailing Pros, Cons, and the explicit **Trade-off** (what you sacrifice when choosing each option).
* Recommend the optimal path based on the user's stated constraints.

### 3. Pre-Mortem Stress Test (Tự phản biện & Tìm điểm gãy)

* Assume the recommended solution has **failed 6 months after deployment**.
* Identify the top 2 to 3 **Single Points of Failure (SPOF)**, edge cases, or operational bottlenecks across technical, user behavior, or cost dimensions.
* Provide a concrete mitigation or fallback mechanism for each identified risk.

### 4. Atomic Execution Plan (Kế hoạch thực thi nguyên tử)

* Break the implementation down into small, sequential, dependency-ordered steps.
* Define a clear, verifiable **Definition of Done (DoD)** or test criterion for each step so progress can be validated immediately before moving to the next phase.

## Gotchas

* **Avoid sycophancy:** Do not praise flawed assumptions. Point out bottlenecks directly and constructively in the Pre-Mortem stage.
* **Keep it proportional:** Scale the depth of the 4 stages to the complexity of the task. Do not write a 2,000-word manifesto for a small module; keep tables and bullet points sharp, concrete, and scannable.
* **Hold off on heavy boilerplate:** Unless explicitly asked to generate full code immediately, lock in the 4-stage blueprint first so the user can verify the architecture before implementation.

---
name: visual-ui-director
description: Directs high-craft UI/UX design systems, 5-layer image generation prompts, and precision delta-based image editing. Use when the user asks to generate images, edit or refine existing images, write image prompts, design UI/UX interfaces, create wireframes or mockups, establish design tokens, or improve visual hierarchy without generic AI clichés.
---

# Visual UI Director

A unified visual direction and UI/UX engineering protocol that eliminates generic "AI slop" interfaces, structures image generation using a 5-layer art direction framework, and enforces anchor-and-delta precision when editing images.

## When to Use

* Generating new images, illustrations, product renders, diagrams, or UI mockups
* Editing, retouching, or modifying specific elements of an existing image while preserving the original composition
* Designing web, mobile, dashboard, or hardware interfaces and design systems (Auto Layout, tokens, component anatomy)
* Translating rough visual ideas into production-grade image prompts or UI specifications

## Steps

Select the operating mode that matches the user's request (or combine Mode 1 and Mode 2 when generating UI mockup images):

### Mode 1: UI/UX Architecture & Anti-Slop Design

Before writing UI code, Figma specs, or UI mockup image prompts, define the following four pillars:

1. **Context & Ergonomics:** Identify the user's real-world environment (e.g., high-glare outdoor use, fast one-handed operation, dense analytical monitoring) to dictate contrast, touch target size, and information density.
2. **Design Tokens & Visual Hierarchy:**
   * **60-30-10 Color Rule:** 60% neutral background/surface (`--bg-surface`), 30% structural cards/containers/borders (`--surface-elevated`), and 10% high-contrast primary actions and semantic status (`--accent-primary`).
   * **Typography & 8pt Grid:** Establish a strict typographic scale (Heading, Subheading, Body, Caption) and enforce spacing in multiples of 4px or 8px so the layout passes the "squint test" (clear hierarchy even when blurred).
3. **Anti-Slop Guardrails:** Explicitly reject generic AI visual clichés: avoid aimless neon purple-blue gradients, heavy muddy drop shadows, unaligned floating cards, or decorative charts with fake, unreadable metrics.
4. **Component Anatomy:** Specify exact, functional UI elements (navigation structure, primary metric cards, clear CTA buttons, and realistic microcopy) before rendering or coding.

### Mode 2: 5-Layer Image Generation Protocol

When crafting image prompts or calling image generation tools, replace disconnected keyword "tag soup" (e.g., *4k, masterpiece, trending, hyper-detailed*) with coherent natural language structured across five layers:

1. **Medium & Style:** State the exact visual format (e.g., *photorealistic studio product photography, clean flat vector illustration, isometric 3D cutaway render, high-fidelity mobile UI mockup*).
2. **Subject & Materiality:** Describe the core subject with concrete physical textures and materials (e.g., *matte bead-blasted aluminum, frosted acrylic, warm natural oak grain, crisp 1px subtle border*).
3. **Environment & Spatial Composition:** Define the background setting, camera angle (*top-down flat-lay, eye-level, macro close-up, 45-degree isometric*), and spatial framing (*rule of thirds, centered hero with generous negative space*).
4. **Lighting & Color Atmosphere:** Specify light sources and mood (*soft diffused window light, crisp rim lighting, warm ambient glow, high-contrast studio softbox*) alongside a cohesive color palette.
5. **Exact Text & Aspect Ratio:** Enclose any required visible text in quotation marks (`"..."`) and select the optimal aspect ratio (`16:9` for widescreen/hero banners, `9:16` for mobile screens, `4:3` for dashboards, `1:1` for icons/avatars). When the user wants an image generated directly, pass this synthesized 5-layer prompt directly into the image generation tool.

### Mode 3: Precision Delta Image Editing

When modifying or refining an existing image, structure the edit instruction into two strict boundaries to prevent unintentional layout drift:

* **Anchor Elements (Keep):** Explicitly state the background, camera angle, lighting, and primary subject details that must remain untouched.
* **Delta Modification (Change):** Describe only the exact addition, removal, color shift, or material swap required, using precise spatial references (e.g., *top-right corner, foreground surface, primary button*).

## Gotchas

* **No keyword stuffing:** Modern image models interpret descriptive sentences about lighting and surface materials far more accurately than comma-separated quality buzzwords.
* **Functional UI over sci-fi concept art:** When generating UI visuals, ground the prompt in clean grid layouts, legible typography, and realistic device frames rather than glowing holographic screens that cannot be implemented in code or Figma.
* **Seamless tool execution:** If the user asks to create or edit an image directly, apply the 5-layer or Delta protocol internally to construct the prompt and invoke the image generation tool immediately rather than only outputting text instructions.

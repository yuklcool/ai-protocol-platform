# DESIGN.md — AI Protocol Platform

> Visual baseline: **Linear-inspired Enterprise Agent Console**
>
> Source reference: VoltAgent/awesome-design-md → `design-md/linear.app/DESIGN.md`
>
> This document is the visual contract for the frontend. Product behavior is defined elsewhere; this file defines how the product should look and feel.

## 1. Design direction

The product is a professional, high-density Agent platform. The UI should feel precise, calm, technical, and fast.

Use a **Linear-inspired** design language:

- dark-first application chrome
- near-black canvas with a small surface ladder
- one restrained lavender-blue primary accent
- 1px hairline borders instead of drop shadows
- 6–12px corner radii
- compact controls and information-dense layouts
- strong typography hierarchy with minimal decoration
- semantic colors only for status / warning / error
- product UI itself is the visual focus

Do **not** copy Linear branding, logos, or proprietary typography. Use the design principles and token structure, adapted to AI Protocol Platform.

## 2. Product information architecture

The visual hierarchy must reinforce four product areas:

```text
Agents
  user-facing AI products

Resources
  Skills / Tools / MCP / Models / Knowledge / Secrets

Administration
  Tenant / User / Group / Permission / Usage / Audit

Developer
  Playground / A2UI / MCP Apps / Protocol Inspector
```

The main navigation should never mix these responsibilities.

## 3. Color system

### Dark theme — primary reference

```text
canvas              #0A0B0E
surface-1           #101217
surface-2           #151820
surface-3           #1A1D26
surface-hover       #20242E

hairline            #272A33
hairline-strong     #343844

ink                 #F5F7FA
ink-muted           #C3C8D0
ink-subtle          #8B929E
ink-disabled        #5E6570

primary             #5E6AD2
primary-hover       #7C86E8
primary-focus       #6873D8
primary-soft        rgba(94,106,210,.14)

success             #2DA44E
warning             #D29922
error               #F85149
info                #58A6FF
```

### Light theme

```text
canvas              #F7F8FA
surface-1           #FFFFFF
surface-2           #F2F4F7
surface-3           #EAEDF2
surface-hover       #EEF1F5

hairline            #E1E5EA
hairline-strong     #C8CED7

ink                 #17191D
ink-muted           #4F5661
ink-subtle          #747C87
ink-disabled        #A0A7B1

primary             #5E6AD2
primary-hover       #4F5BC4
primary-focus       #6873D8
primary-soft        rgba(94,106,210,.10)
```

### Color rules

- Primary lavender-blue is reserved for:
  - primary CTA
  - selected navigation
  - focus state
  - key links
  - active Agent / capability emphasis
- Do not use primary as large card backgrounds.
- Do not introduce decorative gradients in application UI.
- Semantic green / amber / red / blue are for state only.
- Avoid multi-color dashboards unless colors encode meaning.

## 4. Typography

Use only open/system fonts:

```css
font-family:
  Inter,
  Geist,
  "Noto Sans SC",
  "PingFang SC",
  "Microsoft YaHei",
  system-ui,
  sans-serif;
```

Monospace:

```css
font-family:
  "Geist Mono",
  "JetBrains Mono",
  "SFMono-Regular",
  Menlo,
  Consolas,
  monospace;
```

Typography scale:

| Token | Size | Weight | Line height | Use |
|---|---:|---:|---:|---|
| page-title | 24px | 600 | 32px | page title |
| section-title | 18px | 600 | 26px | major section |
| card-title | 15px | 500 | 22px | cards / panels |
| body | 14px | 400 | 21px | default UI |
| body-strong | 14px | 500 | 21px | emphasized UI |
| caption | 12px | 400 | 18px | metadata |
| micro | 11px | 500 | 16px | labels / status |
| mono | 12px | 400 | 18px | ids / trace / code |

Rules:

- Page titles should be compact, not marketing-sized.
- Default product text is 14px.
- Use 500/600 weight for hierarchy; avoid excessive bold.
- Chinese UI should remain visually compact and readable.
- IDs, MCP tool names, model IDs, traces, and JSON use monospace.

## 5. Spacing

4px base unit:

```text
4   micro
8   tight
12  compact
16  default
24  section
32  major section
48  page separation
```

Rules:

- Inputs / buttons should not exceed unnecessary vertical height.
- Prefer 16–24px panel padding.
- Dense management screens can use 12–16px.
- Avoid oversized whitespace that reduces operational visibility.

## 6. Radius

```text
4px   badge / tiny chip
6px   small controls
8px   buttons / inputs / dropdowns
10px  compact panels
12px  cards / dialogs
16px  rare hero or large preview panels
999px status pill only
```

Avoid pill-shaped primary CTAs.

## 7. Elevation

Depth comes from surfaces and borders, not shadows.

```text
Level 0  canvas
Level 1  surface-1 + 1px hairline
Level 2  surface-2 + 1px hairline-strong
Level 3  surface-3 for popover / nested panel
Focus    2px primary-focus ring
```

Rules:

- Default cards: no shadow.
- Dropdown / popover may use one subtle shadow only where necessary.
- Avoid glassmorphism, blur-heavy panels, neon glows.

## 8. Navigation

### App sidebar

Desktop width: 220–240px.

Sections:

```text
Overview

Agents

Resources
  Skills
  Tools
  MCP Servers
  Models
  Knowledge
  Secrets

Administration
  Tenants
  Users & Groups
  Permissions
  Usage
  Audit

Developer
  Playground
  A2UI
  MCP Apps
  Protocol Inspector

Settings
```

Style:

- flat dark surface
- selected item uses `primary-soft` background and primary/ink text
- icons 16–18px, one consistent icon family
- group labels use 11px uppercase/subtle text
- no colorful navigation icons

### Top bar

Height: 48–56px.

Contains only current context and relevant actions. Avoid duplicating sidebar navigation.

## 9. Agent list

Agent cards are operational cards, not marketing cards.

Each card should show:

```text
Avatar + Agent name
short description

Model
Skills count
MCP count

Status
Last updated

Chat      Configure      …
```

Rules:

- 2–3 columns on desktop
- 1px border
- 12px radius
- no gradient background
- status color is semantic
- only user-facing Agents appear here

Internal/system/development Skills belong in Resources or Developer.

## 10. Agent Studio

Desktop layout:

```text
┌───────────────┬───────────────────────────────┬────────────────────┐
│ Studio nav    │ Editor                        │ Test / Preview     │
│ 200–220px     │ min 560px / flexible          │ 360–420px         │
└───────────────┴───────────────────────────────┴────────────────────┘
```

Studio navigation:

```text
Overview
Model
Prompt

Capabilities
  Skills
  Tools
  MCP

Knowledge
Interaction
Permissions
Advanced
```

Rules:

- editor sections should feel like settings panels, not giant forms
- use section headers + concise help text
- progressive disclosure for advanced settings
- sticky Save / Publish actions
- right preview panel remains visible on wide screens
- at <= 1100px preview becomes a drawer/tab
- at mobile, Studio becomes single-column

## 11. Forms

Inputs:

- height 36–40px desktop
- 8px radius
- surface-1 background on dark
- clear 1px border
- primary focus ring
- labels 12–13px
- helper text 12px subtle

Do not stack dozens of fields in one endless page. Split by task.

Selects that expose technical objects should show:

```text
Human-readable name
secondary technical id / provider
status or capability
```

Example:

```text
GPT Sol
OpenAI-compatible · gpt-5.6-sol
Tool calling · Reasoning · Streaming
```

## 12. Buttons

Primary:

- 36px height
- primary background
- white text
- 8px radius

Secondary:

- surface-2 background
- 1px hairline
- ink text

Ghost:

- transparent
- muted text
- surface-hover on hover

Danger:

- neutral by default where possible
- error color only at destructive confirmation/action

Avoid having 3+ primary-looking buttons in one region.

## 13. Status

Use dot + label:

```text
● Online
● Draft
● Published
● Warning
● Disabled
● Error
```

Use compact neutral pills only when a badge is necessary.

Do not encode status by color alone; always include text/icon.

## 14. Capabilities

Skills / Tools / MCP use the same selection pattern.

Two-pane picker where useful:

```text
Available                     Selected
────────────────────────────────────────
Search                        3 selected

Skill A      +                Skill X ×
Skill B      +                Skill Y ×
Skill C      +                Skill Z ×
```

Each resource row shows:

- icon
- name
- concise description
- health / availability
- permission state when relevant

## 15. MCP

MCP server cards should emphasize operational state:

```text
lighting-mcp                         Online

Streamable HTTP
12 Tools · 3 Resources · 2 Prompts
MCP Apps supported

Used by 2 Agents

Configure     Diagnose
```

Do not make “bind Skill” the primary action in MCP Registry.

Agent binding belongs in Agent Studio → MCP.

## 16. Permissions

Permission UI should prioritize **effective access**.

Use a compact matrix:

| Resource | Requested | Tenant | Group/User | Effective |
|---|---|---|---|---|
| GPT Sol | yes | allow | allow | Allowed |
| lighting-mcp | yes | allow | allow | Allowed |
| device-control | yes | allow | deny | Denied |

Denied state must include the reason.

## 17. Test / Preview

The preview panel should look like the production Chat UI, not a debug console.

Default view:

- user message
- Agent answer
- compact tool/MCP activity rows
- A2UI surface preview

Expandable diagnostics:

- provider / model
- latency
- token usage
- tool call
- MCP call
- permission denial
- A2UI surface/action
- run error

Technical diagnostics use mono text and surface-2 rows.

## 18. Chat

Chat is an end-user surface.

Do:

- conversation sidebar
- current Agent identity
- clean message stream
- A2UI surfaces inline/workspace
- New Chat
- optional compact activity detail

Do not:

- expose full platform admin controls
- expose internal/system/development Skills in Agent switcher
- show raw runtime config by default

## 19. Resources

Resources pages should use dense list/table views by default, not oversized card galleries.

Recommended structure:

```text
Page title                    + Add
Search   Filter   Status

Name             Type       Status     Used by      Updated
──────────────────────────────────────────────────────────
lighting-mcp     MCP        Online     2 Agents     2m
alarm-analysis   Skill      Ready      4 Agents     1h
GPT Sol          Model      Ready      3 Agents     3h
```

Cards are appropriate only for visually distinct user-facing Agents.

## 20. Tables

- row height 40–44px
- sticky header for long lists
- subtle row hover
- no zebra stripes
- right-align numeric data
- use monospace for IDs and usage values where helpful
- actions remain on the right
- pagination compact

## 21. Icons

Use one icon family (Lucide preferred).

- 16px standard
- 18px primary nav
- 20px feature/action only
- no emoji as production navigation icons
- no mixed outline/filled icon languages

## 22. Motion

Motion should communicate state, not decorate.

```text
hover/focus       120–160ms
panel transition  160–200ms
drawer/modal      180–220ms
```

Use ease-out.

Avoid:
- bounce
- excessive spring motion
- animated gradients
- decorative particles

## 23. Responsive behavior

### >= 1280px
Full sidebar, multi-column Agents, three-column Studio.

### 1024–1279px
Sidebar compact; Agent Studio preview becomes collapsible.

### 768–1023px
Sidebar becomes drawer; cards 2-up; Studio editor single main column + preview tab.

### < 768px
Single-column management experience; touch targets >= 44px.

Chat remains optimized for conversation.

## 24. Accessibility

- WCAG AA contrast minimum
- visible keyboard focus on every interactive control
- labels attached to inputs
- status not color-only
- no hover-only critical action
- table rows keyboard navigable where interactive
- dialog focus trap
- reduced-motion support

## 25. Do

- keep the canvas calm and dark
- use a surface ladder for hierarchy
- use one restrained primary accent
- use 1px borders
- keep operations dense and legible
- expose state clearly
- make Agent Studio task-oriented
- use Resources tables for infrastructure
- reserve cards for Agents and previews

## 26. Don't

- no neon sci-fi dashboard aesthetic
- no glassmorphism
- no decorative gradients in core app
- no giant glowing cards
- no multiple bright accent colors
- no excessive pills
- no 20px+ body text in admin screens
- no endless single-page settings forms
- no internal Skill / Demo mixed into user Agent navigation
- no technical JSON fields unless in Advanced / Debug
- no random per-page styling

## 27. AI implementation prompt

When generating or modifying frontend UI:

> Use the AI Protocol Platform DESIGN.md. Follow the Linear-inspired Enterprise Agent Console language: compact dark-first product UI, four-level neutral surface hierarchy, 1px hairline borders, 8–12px radii, restrained lavender-blue primary, Inter/Geist typography, no gradients/glassmorphism, dense but calm admin layouts, and clear semantic status. Preserve the product hierarchy Agents → Resources → Administration → Developer. User-facing Agents are cards; infrastructure resources are lists/tables; Agent Studio is a three-column configuration + preview workspace.

This file is the visual source of truth for all v1.1 frontend redesign work.

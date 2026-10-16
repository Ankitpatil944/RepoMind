# RepoMind — DESIGN.md

Local, no-AI-required web tool that helps a developer understand an unfamiliar Python / JS / TS codebase.
Tone: elegant editorial serif headlines on a dark terminal canvas. Muted colors, no neon. Rich but purposeful motion.

Reference prototype: `design/Main.dc.html` (custom format — use as a spec, do not copy the markup).

---

## 1. Tokens

### Color (one accent per meaning)
| Token | Hex | Meaning |
|---|---|---|
| `ink` | `#0b0e11` | App background |
| `panel` | `#0e1217` | Header, nav, inspector |
| `card` | `#11151a` | Cards |
| `raised` | `#161b21` / `#1e252d` | Buttons, menus, hover |
| `line` | `#222a33` / `#2d3742` | Borders |
| `text` | `#dce3ea` | Body |
| `muted` | `#94a1ae` / `#7d8a97` | Secondary text |
| `cream` | `#f1ece0` | Display / headline text |
| `sage` | `#b9c79a` | Interactive: selection, primary button, citations, root node, focus ring |
| `terracotta` | `#d98a62` | Risk: public endpoints, high complexity |
| `brass` | `#cfae6a` | Mid complexity, JavaScript |
| `teal` | `#7fb0b4` | Calls / links / hover highlight, Python |
| `lavender` | `#a79fc7` | TypeScript, authentication |
| `moss` | `#8fb996` | Low complexity, "live" dot, AI-on |

Sage tints: bg `#1d231a`, border `#4a573b` / `#5c6b49`, hover `#262e20`, text-on-sage `#12160d`.
Complexity thresholds: `cx >= 10` terracotta, `cx >= 6` brass, else moss.
Treemap heat: interpolate tile bg `rgb(21,36,44)` → `rgb(100,56,40)` and border `rgb(42,74,88)` → `rgb(217,138,98)` by normalized peak complexity of the file.

### Type
- Display: **Instrument Serif** (headlines, big stat numbers, section titles, inspector lead). Italic for emphasis words.
- UI: **Geist** 400/500/600, 13px base, line-height 1.45.
- Code / paths / metrics: **Geist Mono**.
- Labels: 11px, uppercase, `letter-spacing: .09em`, 600, `muted`.

### Shape / spacing
- Radius: 7px controls, 10–12px cards, 999px chips/pills.
- Gutter 20px, grid gap 12px. Dot-grid background `radial-gradient(#1b222a 1px, transparent 1px)` 22px.
- Focus: 2px sage outline, 2px offset.

---

## 2. Layout

```
Header: logo · repo picker · Index project · Export · AI on/off pill · ask box (/) · ⌘K palette
Nav:    Overview · Architecture · Call flow     (sliding sage underline)   status line
Body:   [ main view ] [resize handle] [ Inspector 300–680px, default 400 ]
```
Inspector tabs: **Summary · Source · Evidence · Explain** (sliding underline). Header of the inspector has a Back button (selection history, last 20), badges, mono title and sub path.
Below 900px: stack vertically, inspector goes under main, status line hidden.

---

## 3. Views

### Overview
Sections in order, each introduced by a numbered serif label (`01 Begin here`, `02 The shape of it`, `03 Where the risk lives`, `04 Guards and dependencies`):
1. **Briefing hero** — `~/ briefing` mono label, giant serif headline (word-by-word rise), e.g. "38 endpoints, 8 wide open. One guard holds the rest." Three clickable **findings** (tag + sentence + arrow) that jump to call flows.
2. **Start here** — 4 cards, 3D tilt on mouse move.
3. **Stat row** — Files, Lines, Functions, Classes, Endpoints; serif numerals that count up.
4. **Language mix** + **Auth surface** — segmented bars that grow in; Public segment breathes.
5. **Risk map** — squarified treemap; size = lines, heat = peak complexity; hover dims others and shows a readout line; hot tiles pulse.
6. **Hotspots** — Most called / Most complex / Largest (top 5 each).
7. **Auth guards** and **Third-party libraries** (bar list).

### Architecture
Folder dependency map. Node size = code volume, arrows = imports (curved, weight by count). Double-click a folder to drill into its files; ghost dashed folders show outside importers (left) and imports (right). Breadcrumb chips. Hover: node scales 1.07 with teal glow, neighbors stay, others dim, edge chip shows import count. Selected node: sage glow + rotating dashed orbit ring.

### Call flow
Node-link graph (React-Flow style). Root chips, Calls / Callers / Both, depth stepper (1–4), outline toggle, Fit / − / + zoom.
- Node: badge (EP / FN / TSX / EXT), name, signature (2 lines), docstring, size + complexity + fan-in/out, 10-tick complexity meter, left/right ports.
- External calls (e.g. `jwt.decode`) are dashed and labeled "external · not indexed".
- Drag to pan, minimap with draggable-looking viewport, click minimap to jump.
- Edges: dark underlay + flowing dashed line + traveling packet dots. Hover → faster flow, teal glow, line-number chip (`L42`), unrelated nodes dim to 30%. Edges touching the selected node turn sage.

---

## 4. Inspector content
- **Summary**: serif plain-language lead, docstring, signature, metrics, lists (calls / called by), actions.
- **Source**: highlighted code with line numbers; cited line is highlighted.
- **Evidence**: grouped citations (`file:line`) for every claim.
- **Explain**: bullet explanations; AI card shows "AI is off" by default. Everything works without a model; AI only rephrases indexed facts and must cite lines.

Ask box: answers are built from the static index, each line has citation buttons (`path:line`). Suggested questions when empty.

---

## 5. Motion system
Principle: motion explains structure; it never blocks work. Everything stays interactive during animation.

| Moment | Effect |
|---|---|
| **Intro (envelope)** | Pick a repo → seal fades, flap rotates 180° (`rotateX`), letter slides up then scales to fill screen, gate fades. Timeline ≈ 2.95s to fade, 3.65s to remove. Mouse parallax on glyph field and envelope. "Skip intro" always visible. |
| Dashboard load | Staggered `rise` (translateY 16px) per section; hero words `wordrise` (blur → sharp), bars `grow`, tiles `pop`, stat numbers count up (1.5s, ease-out cubic). |
| View switch | Fade + 12px rise + 5px blur, 600ms. Nav underline slides 450ms. |
| Cursor spotlight | Soft radial sage tint follows pointer (rAF-throttled, CSS vars). |
| Cards | 3D tilt ±9° on hover. |
| Edges | Dash offset animation (3.2s idle, 0.9s hot), packets along `offset-path`, fade-in staggered by index. |
| Nodes | Pop-in staggered 60–70ms; hover lift/scale; ring pulse on hot, orbit on selected; complexity ticks grow in. |
| Indexing | Scan beam sweeps the main view. |
| Idle | Live dot pulse, subtle sweep on stat cards, shimmer on bars. |

Gate dashboard animations until the intro finishes (pause via `animation-play-state`).
Use `backwards` fill (not `both`) so hover/dim transforms still work.
**Respect `prefers-reduced-motion`**: collapse durations to ~0 and run once.

---

## 6. Interaction & a11y
- `/` focuses ask box; `⌘/Ctrl K` opens command palette; `Esc` closes popovers.
- Inspector is resizable (300–680px).
- Every node/tile is a real `button` with an `aria-label` (name, complexity, auth).
- Color is never the only signal: badges, text labels and dashed borders back it up.
- Keep contrast ≥ 4.5:1 for body text on `ink`.

---

## 7. Data model the UI expects
```
Node   { id, name, kind: 'ep'|'fn'|'cmp'|'ext', file, ln, sig, doc, loc, cx, fi, fo,
         route?, auth?: 'public'|'authentication'|'protected', guard?, pkg?, src }
Edge   [callerId, calleeId, callLine]
File   { id, name, path, folder, lang: 'py'|'ts'|'js', loc }
Import [fromFileId, toFileId]
Folder { id, files, loc, group: 'py'|'ts' }
Totals { files, lines, fns, classes, eps }
```
Layouts to implement: BFS by depth/mode + longest-path ranks + barycenter ordering (call flow); force-free fixed folder positions or force layout (architecture); squarified treemap (overview).

---

## 8. Build notes
- Suggested stack: React + TypeScript + Vite, CSS variables for tokens, SVG for edges, `offset-path` for packets.
- Keep graph rendering DOM/SVG based (≤ ~200 nodes); virtualize beyond that and show the "large repo" state.
- States still to design: empty repo, indexing error, very large repo, narrow/mobile.
- Never send code off-machine by default; the UI says so ("nothing left this machine").

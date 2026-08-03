# AgentConvos TUI design brief

## Product outcome

Let a developer orient to the current project, find a recent coding-agent conversation, and read its complete rendered context without leaving the keyboard.

## Users and environment

- Primary user: a developer reviewing recent Codex, Claude, Pi, Agy, OpenCode, or Clihow work.
- Host: standalone terminals and tmux panes; sessions are frequent and may stay open while other work continues.
- Review sizes: `136x65` for the adjacent demonstration pane and `90x30` for compact use.
- Minimum useful size: `72x18`; below that, show a concise resize state instead of broken panes.
- Keyboard operation is complete. Mouse capture, Nerd Fonts, animation, and truecolor are not required.
- Color supplements words, row shape, and position; it never carries focus or status alone.

## Primary tasks

| Task | Frequency | Cost of error | Desired shortest path |
|---|---:|---:|---|
| Orient to project and recent work | High | Medium | Launch, read header and selected row |
| Select another conversation | High | Low | Arrow or `j`/`k`; detail refreshes immediately |
| Read a complete reply | High | High | `Tab`, then arrows/`j`/`k` or `PgUp`/`PgDn` |
| Filter recent conversations | Medium | Low | `/`, type, inspect count, `Enter` or `Esc` |
| Recover from a filter | Medium | Medium | `Esc` clears search and restores prior selection when available |

## Information priority

1. Must dominate immediately: project identity, selected conversation title, and readable conversation content.
2. Must remain visible during work: result count/position, focus, search state, and detail scroll state.
3. Useful supporting context: date, source agent, turn count, model, effort, and short conversation ID.
4. Can move into detail/help: complete first/latest-user/latest-agent messages and secondary key hints.
5. Can be removed: decorative branding, redundant labels, duplicated first/latest-user text, empty metadata, and ornamental borders.

## Interaction contract

```text
launch real project context -> orient -> select or filter -> immediate detail feedback -> read/scroll -> select again or clear -> Ctrl+C to leave
```

- Focus order is list then detail. `Tab` and `Shift+Tab` traverse the same two-region cycle.
- List focus routes arrows and `j`/`k` to selection. Detail focus routes arrows, `j`/`k`, `PgUp`/`PgDn`, Home/End, and `g`/`G` to the viewport.
- `/` enters the Bubbles filter input and moves focus to the list. Ordinary input is owned by that component.
- `Enter` accepts an active filter. `Esc` cancels/clears search first; with no temporary state it remains in the app.
- `Ctrl+C` is the unambiguous exit. There are no destructive actions in this slice.
- Selection is tracked by stable conversation identity and remains visible, but quieter, while detail is focused.

## Aesthetic direction

Desired qualities:

```text
1. Calm and confident
2. Warm and editorial
3. Purposeful and product-quality
```

Anti-goals:

```text
1. Cyber-console decoration
2. Sterile data dump or timid near-monochrome styling
3. Rainbow color, nested boxes, or border soup
```

Density target: balanced and compact enough for continuous browsing.

Reference language: polished Charm applications, with a compact header, meaningful surfaces, full-width selected rows, a strong reading pane, and contextual footer help.

## Semantic visual tokens

- Warm charcoal/ink canvas with one slightly raised panel surface.
- Soft ivory primary text and legible taupe muted text.
- One lilac main accent for active focus and primary identity.
- Deep plum selected row; quieter neutral-plum inactive selection.
- Amber match treatment for the active query/result explanation.
- Sage status treatment for scroll state; red reserved for actual errors.
- Focus is conveyed by an accent rail/title and the footer focus word, not color alone.
- Plain text labels and common glyphs (`/`, `|`, `>`/`▌`) provide safe fallbacks.

## Real content samples

- Long title: `For THIS task you are the sole implementation worker, not an orchestrator.`
- Current work: `Finish a thin, polished, real-data AgentConvos Bubble Tea UI slice for visual approval.`
- Metadata: `03 Aug · codex · 10 turns` and `gpt-5.6-sol · max`.
- Empty result: `No conversations match “bubble tea”. Esc clears the filter.`
- Startup failure: `agentconvos-tui: load project context: ...` remains a concise stderr error before the alternate screen starts.
- Long detail: complete Markdown headings, lists, links, emphasis, and fenced Go code ending in a unique tail marker.

## Layout matrix

| State | Too small (`<72x18`) | Compact (`90x30`) | Wide (`136x65`) |
|---|---|---|---|
| Initial/populated | Resize message with current/required dimensions | Two panes; compact 34-cell browse rail and flexible detail | Two panes; approximately 44-cell browse rail and dominant detail |
| Filtering | Same resize message | Search row stays visible; count becomes `n results of total` | Same, with more title/metadata room |
| Empty filter | Same resize message | Browse pane explains no match; detail repeats recovery cue | Same without wasting the reading surface |
| Detail focused | Same resize message | Selected row remains as a subdued full-width band | Selected row remains visible; detail focus rail/title is accented |
| Long content | Same resize message | Soft-wrapped viewport scrolls to the actual tail | Wider Markdown measure with the same complete source content |

Every supported canvas uses one header row, one footer row, and a body of exactly `height - 2`. The panes have no nested box borders; one separator and surface changes provide structure.

## Keymap

### Global

| Key | Action | Why global |
|---|---|---|
| `Ctrl+C` | Quit | Reliable fallback that never conflicts with ordinary text |
| `Tab` / `Shift+Tab` | Move list/detail focus | Fixed major-region focus order |
| `/` | Enter filter | Primary retrieval action outside text-entry mode |

### Contextual

| Focus/mode | Key | Action |
|---|---|---|
| List | arrows or `j`/`k` | Select conversation and refresh detail |
| Detail | arrows or `j`/`k` | Scroll by line |
| Detail | `PgUp`/`PgDn` | Scroll by page |
| Detail | Home/End or `g`/`G` | Go to beginning/end |
| Filter | ordinary text/paste | Update Bubbles filtering only |
| Filter | `Enter` | Apply filter |
| Filter/applied filter | `Esc` | Cancel or clear, then restore browse context |

## Acceptance criteria

- Real `agentconvos --context --json` data populates the application.
- Context, count/position, focus, query/filter state, and scroll state are visible at a glance.
- Selection, focus, inactive selection, match/query, and status have distinct treatments.
- List rows always render exactly their declared two-line height and selected bands fill the pane.
- Detail content is Glamour v2 Markdown, soft-wrapped, complete, and scrollable to its true tail.
- `136x65` and `90x30` render to exact Lip Gloss dimensions with an on-canvas footer.
- Search owns ordinary typing; its Escape ladder and stable selection are covered by tests.
- No resume, handoff, source-opening, launcher, packaging, or default-command work enters this slice.

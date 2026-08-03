# AgentConvos conversation journal — design brief

## Product outcome

Give a developer a memorable, calm place to revisit recent coding-agent work: scan the recency trail, understand the selected conversation's purpose and latest concrete outcome, then read the complete exchange without leaving the keyboard.

This is a premium conversation journal / field-notes workspace. It is not a database browser with nicer colors.

## Acceptance artifact diagnosis

The rejected medium-pane screen keeps the same database-browser skeleton as the first prototype: a hard vertical split, an always-empty filter row, uniform three-line records, and a generic metadata card followed by a transcript dump. The left pane has no recency rhythm and leaves a large dead area; the right pane gives labels and chrome more authority than the selected purpose or outcome. Lavender is responsible for brand, focus, selection, links, and hierarchy, so nothing feels singular. The header and footer read like framework scaffolding. The composition needs a different reading model, not another palette or spacing pass.

## Users and environment

- Primary user: a developer revisiting recent Codex, Claude, Pi, Agy, OpenCode, or Clihow work.
- Data source: the real `agentconvos --context --json` payload for the current project.
- Review canvases: luxurious `150x40`, adjacent-pane `109x33`, and compact `90x30`.
- Minimum useful canvas: `72x18`; below it, show a deliberate resize state.
- Keyboard operation is complete. No mouse dependency, Nerd Font, animation, gradient, or fake data.
- Color supplements labels, shape, position, and spacing; it never carries state alone.

## Primary tasks

| Task | Frequency | Cost of error | Desired shortest path |
|---|---:|---:|---|
| Understand the selected work and outcome | High | High | Launch and read the hero/outcome |
| Move through recent work | High | Low | Arrow or `j`/`k`; reading sheet updates immediately |
| Read the complete reply | High | High | `Tab`, then scroll by line/page/to tail |
| Find a conversation | Medium | Low | `/`, type in the transient search strip, inspect count |
| Recover from search or compact reading | Medium | Medium | Predictable `Esc` ladder without quitting |

## Information priority

1. Selected purpose/title and exact latest outcome.
2. Human/agent exchange in readable Markdown.
3. Recent-conversation navigation.
4. Date, coding agent, turns, model, effort, and short identity.
5. Contextual key help.

Empty metadata is omitted. When the backend has no summary/recap field, the UI does not invent one: **Latest outcome** is a restrained excerpt of the exact latest agent message, while the full message remains below. Delegated conversations whose prompt was not recorded say so honestly. Identical first/latest-user content is shown once.

## Interaction contract

```text
launch real context -> understand selected note -> browse or search -> Tab to read -> scroll complete reply -> Tab back or Esc recover -> Ctrl+C leave
```

- `Tab` and `Shift+Tab` move between the recency feed and reading sheet.
- Feed focus routes arrows and `j`/`k` to selection; selection refreshes the reading sheet immediately.
- Reading focus routes arrows and `j`/`k` by line, `PgUp`/`PgDn` by page, and Home/End or `g`/`G` to limits.
- `/` opens a focused Bubbles search strip. There is no vacant filter row while browsing.
- Ordinary typing is owned by the search input. `Enter` applies; `Esc` first cancels/clears search.
- At compact width, `Esc` from the reading mode returns to the feed; it never quits. `Ctrl+C` is the unambiguous exit.
- Selection is tracked by stable conversation identity across filtering, focus changes, and breakpoints.

## Aesthetic direction

Desired qualities:

```text
editorial · tactile · confident · composed · memorable
```

Anti-goals:

```text
database admin · transcript dump · cyber/gamer console · purple everywhere
border soup · dashboard cards · generic Bubbles defaults
```

The visual metaphor is a field journal: a graphite recency trail beside a subtly raised warm reading sheet. Hierarchy comes from composition, measure, type treatment, whitespace, rails, and layered surfaces—not boxes around every region.

## Semantic visual tokens

- `canvas`: near-black graphite, the quiet outer field.
- `feed`: slightly lifted ink for recent-note navigation.
- `paper`: warm charcoal/brown-black reading surface.
- `raised`: a restrained warmer outcome surface.
- `text`: warm ivory; `muted`: readable taupe; `faint`: subdued structural copy.
- `signature`: vivid vermilion/coral, reserved for brand, active focus rail, selected marker, and active search cursor.
- `question`: restrained sea-glass teal for human speaker language.
- `answer`: ochre/gold for agent/outcome language.
- `status`: sage for healthy scroll/result state.
- `selected`: deep ember surface; `inactiveSelected`: quieter warm graphite.
- `separator`: low-contrast warm graphite used only for authored rules and timeline marks.
- `error`: reserved red, never decoration.

There is no lavender/purple identity color. The signature accent is scarce enough to remain meaningful.

## Composition

### Wide and medium: journal + reading sheet

- A two-line authored masthead integrates `agentconvos`, `FIELD NOTES`, project identity, result count/position, focus, and the compact `/ search` affordance.
- The recency feed is not boxed. Entries form a timeline rhythm with a marker/rail, one compact title line, and one stable metadata line; date aligns to the far edge. The selected entry is full width.
- Focused selection uses a vermilion rail/marker and ember field. Inactive selection keeps the same shape with a quieter field and muted rail.
- A two- or three-cell gutter replaces the hard vertical divider.
- The reading sheet begins with a large wrapping title, restrained metadata band, and a clearly separated **Latest outcome** excerpt.
- The exchange follows as an editorial timeline with speaker language: `You opened with`, optional `You asked next`, and `Agent answered`; delegated missing prompts use `Task opened`.
- The latest reply is complete Glamour v2 Markdown, soft-wrapped to the reading measure and scrollable to the actual final line.

### Compact: intentional single-pane modes

- At `90x30`, the feed and reading sheet are separate full-canvas modes rather than squeezed columns.
- Feed mode shows the authored masthead, recency trail, selected position, and a small selected-note outcome cue when room permits.
- Reading mode shows the complete hero/timeline viewport. `Tab` returns to the feed; `Esc` is an additional recovery path.
- Query, stable selection, focus, and viewport state survive transitions across the breakpoint.

### Search

- Browse state shows only a compact `/ search` affordance in the masthead/footer.
- Pressing `/` opens a deliberate full-width search strip directly below the masthead, with query, result count, and `Esc clear` language.
- An applied query collapses back to a compact, explicit filter status; no empty input row remains on screen.
- Empty results use the feed surface for a concise recovery message and never fabricate detail.

## Layout matrix

| State | `150x40` | `109x33` | `90x30` |
|---|---|---|---|
| Initial | ~42-cell journal feed, 3-cell gutter, luxurious reading sheet | ~36-cell feed, 2-cell gutter, composed reading sheet | Full-width feed mode |
| Reading focus | Feed remains visible with quiet selection | Same, with narrower hero measure | Full-width reading mode |
| Search active | Full-width strip below masthead; body loses one row | Same | Full-width strip above feed results |
| Applied filter | Compact query/count in masthead | Same | Same; single-pane state preserved |
| Long reply | Complete viewport to actual tail | Complete viewport to actual tail | Full-width viewport to actual tail |
| Empty results | Recovery copy in feed; no fake reader | Same | Full-width recovery copy |

Every supported canvas measures exactly to the reported width/height using Lip Gloss measurement. Header and contextual footer remain on-canvas. The body absorbs optional search-strip height without clipping.

## Authored chrome

- Masthead tone: publication name + notebook identity, not a logo or dashboard toolbar.
- Footer tone: calm command bar with contextual groups and a right-aligned state phrase (`BROWSE 04/06`, `READ 62%`, `SEARCH 2/6`).
- Bubbles help remains meaningful, but its rendered language is composed into the product instead of displayed as a loose default-widget string.

## Acceptance criteria

- Real `agentconvos --context --json` data populates the UI; no fixtures or inferred summary drive the visible design.
- Selected title and exact latest-outcome excerpt dominate before metadata and help.
- Feed entries have a visible recency rhythm, two-line declared delegate height, stable metadata, and full-width active/inactive selection shapes.
- Search has no permanent vacant row; active input is obvious and owns ordinary typing.
- Wide and medium use the journal/reading-sheet composition with no hard divider or generic pane card.
- Compact is a deliberate feed/read mode, preserving state across focus and resize.
- Conversation Markdown is rendered by Glamour v2, complete, soft-wrapped, and scrollable to its real tail.
- `150x40`, `109x33`, and `90x30` are exact, footer-on-canvas layouts; `<72x18` is an intentional resize state.
- No resume, handoff, source-opening, launcher, packaging, or default-command work enters this slice.

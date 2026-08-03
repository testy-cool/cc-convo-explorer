# AgentConvos TUI implementation plan

## Objective

Deliver a real-data, browse/detail AgentConvos workspace whose geometry, keyboard routing, filtering, and complete Markdown reading experience are ready for visual approval.

## Existing constraints

- Module: Go `1.25.8`; host toolchain `/home/testycool/.local/bin/go` reports Go `1.26.5`.
- Installed stack: Bubble Tea `2.0.8`, Bubbles `2.1.1`, Lip Gloss `2.0.5`, Glamour `2.0.1`; all imports remain `charm.land/.../v2`.
- `loadContext` already consumes `agentconvos --context --json` (or `AGENTCONVOS_BACKEND`) before launching the TUI.
- Scope is browse/detail, focus, scrolling, and local Bubbles filtering only.
- Review terminals are tmux/private PTY at `136x65`, the reported `106x30` medium pane, and `90x30`; minimum is `72x18`.
- No mouse capture, animation, background work, subprocess handoff, or new adapters are needed.

## Primary user flow

```text
launch -> identify project/selection -> browse or / filter -> see detail update -> Tab to read -> scroll to tail -> Esc clear or Tab browse -> Ctrl+C exit
```

The likely next action after reading is selecting another conversation, so list selection and filter context stay intact.

## Information hierarchy

- Dominant: project, selected title, and current conversation message content.
- Persistent: result count/position, focus word, query/filter state, and viewport scroll status.
- Secondary: date, source, turns, short ID, model, and effort.
- Detail-only: full first message, non-duplicate latest user message, and full latest agent reply.
- First to disappear: redundant labels and empty metadata; important narrative content wraps instead of truncating.

## Screens, modes, and overlays

- Browse mode: list focused, detail visible.
- Reading mode: detail focused, list selection remains visible but inactive.
- Filter mode: Bubbles filter input owns ordinary keys; no modal or extra screen.
- Too-small mode: concise resize instruction while model/query/selection state remains intact.
- There are no overlays, launchers, action menus, or external-process screens in this slice.

## Focus order and keys

- Global: `Ctrl+C`; `Tab`/`Shift+Tab`; `/` only outside filter editing.
- Browse: arrows and `j`/`k` go to Bubbles list.
- Reading: arrows, `j`/`k`, `PgUp`/`PgDn` go to Bubbles viewport; Home/End and `g`/`G` jump.
- Filter: the list’s `FilterInput` receives ordinary typing and paste; `Enter` applies; `Esc` cancels/clears.
- No bare letter quits. Contextual Bubbles help is rendered in the footer.

## Model state

- Canonical `contextPayload` and Bubbles list items.
- Explicit `paneFocus` (`browseFocus`, `detailFocus`).
- Terminal dimensions and a computed `paneLayout`.
- Stable selection identity captured when filtering begins and restored when possible.
- Bubbles `list.Model`, `viewport.Model`, and `help.Model`.
- Semantic palette and dark/light background choice.

## Messages

- `tea.BackgroundColorMsg`: update palette and cached Markdown presentation.
- `tea.WindowSizeMsg`: recalculate exact body/pane/component dimensions and re-render wrapping.
- `tea.KeyPressMsg`: global routing, filter ownership, focus switching, then focused component routing.
- Bubbles filter completion messages: update visible results and restore the selection anchor when it remains visible.

There are no custom async messages in this thin slice.

## Commands and adapters

- Startup adapter: `agentconvos --context --json`, structured JSON, invoked once before the Bubble Tea program starts.
- Bubbles may return cursor-blink and local filtering commands; parent update retains them.
- Startup errors remain actionable stderr and non-zero exit. There is no in-app retry because backend lifecycle changes are outside this slice.

## Layout matrix

- Chrome: header `1`, footer `1`, body `height - 2`.
- Wide `136x65`: browse pane about `44`, one-cell separator, detail receives the remainder; body height `63`.
- Medium `106x30`: browse pane `42`, one-cell separator, detail uses two-cell horizontal reading insets; body height `28`.
- Compact `90x30`: browse pane about `34`, one-cell separator, detail receives the remainder; body height `28`.
- Pane children use the exact assigned width. There is no parent horizontal padding that can make a delegate’s declared width wrap.
- Browse body: pane heading `1`, search row `1`, list gets `body - 2`; delegates reserve three rows for up to two humanized title lines and metadata.
- Detail body: pane heading `1`, viewport gets `body - 1` inside a two-cell horizontal reading inset.
- Too-small `<72x18`: exact-size resize view, preserving state for the next resize.

## Visual system

- Qualities: calm, confident, warm, purposeful. Anti-goals: cyber-console, sterile dump, rainbow/border soup.
- Balanced density with three-cell rows, wrapped titles, stable adjacent metadata, and one-cell grouping rhythm.
- Central roles: canvas, panel, raised surface, text, muted, border/separator, accent, selected, inactive-selected, match, status, error.
- Focus: accent pane-title rail plus footer word. Selection: full-row background. Inactive selection: quieter full-row background. Match: amber query treatment. Status: sage scroll label plus text.
- One vertical separator; no rounded boxes around both panes, decorative logo, or animation.

## Interaction continuity

- Selection is identified by stable UUID/source/timestamp/message identity.
- Search captures the pre-filter selection, keeps it when still visible, and restores it after clear.
- Resize preserves focus, query, selection, and viewport offset when content identity does not change.
- Selection changes intentionally reset detail to the top; focus changes do not.
- Re-rendering Markdown for width/theme preserves full source content; scrolling can reach the final line.

## States and copy

- Populated browse: `Recent`, selected row, full detail.
- Filtering: visible `/ query`, `n results of total`, `FILTER` footer state.
- No match: `No conversations match “query”. Esc clears the filter.`
- Too small: `AgentConvos needs at least 72x18` plus current size.
- Startup error: `agentconvos-tui: load project context: <cause>`.
- Missing fields are omitted; identical first/latest-user messages render once.

## Tests and review evidence

- Preserve the existing failing delegate-height/footer geometry tests and observe red then green.
- Add red tests for `Shift+Tab`, Ctrl+C-only exit, search selection restoration, duplicate-message omission, exact `136x65`/`106x30`/`90x30` geometry, wrapped/humanized rows, reading insets, and too-small rendering.
- Keep existing tests for contextual help, list/detail routing, complete tail access, Bubbles filtering, full-width selection, and Glamour Markdown.
- Run gofmt, vet, `go test -p 1 ./...`, build, and a capped serialized race pass if practical.
- Walk through real backend data in private PTYs at all review dimensions and inspect captured screens.
- Complete `docs/review-checklist.md` and `docs/aesthetic-ergonomic-scorecard.md`; target at least `20/24` with no zero.

## Acceptance criteria

- Exact supported geometry and complete content.
- Obvious but restrained focus/selection hierarchy.
- Predictable keyboard grammar and Escape ladder.
- Stable search context and contextual help.
- Real backend walkthrough succeeds at both target dimensions.
- Only the approved UI slice and directly relevant tests/docs change.

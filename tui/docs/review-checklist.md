# AgentConvos conversation-journal review checklist

Reviewed on 2026-08-04 against six real `agentconvos --context --json` conversations, the rejected `/tmp/codex-clipboard-YwTO7V.png` artifact, the Bubble Tea TUI skill v1.1 checklist, and private-PTY captures at `150x40`, `109x33`, and `90x30`.

This checklist verifies completeness and coherence. Its score does not substitute for the user's visual approval.

## Product and information architecture

- [x] The outcome, top tasks, hierarchy, and rejected-screen diagnosis are explicit in `design-brief.md`.
- [x] The first screen identifies `agentconvos`, `FIELD NOTES`, project, result count/position, focus, and `/ search`.
- [x] Selected purpose and exact latest outcome dominate metadata and help.
- [x] Generic detail headings, the permanent filter row, hard pane divider, repeated footer position, and decorative pane chrome were removed.
- [x] The full opening/latest-user/latest-agent content remains readable through the reading viewport.
- [x] Feed title truncation reveals the full wrapping title immediately in the reading sheet or by `Tab` at compact width.
- [x] Empty backend summary data is not replaced by inference; the fallback is an exact first meaningful line from the latest agent message.

## Correctness and architecture

- [x] `go.mod` and imports stay on one Charm major: Bubble Tea/Bubbles/Lip Gloss/Glamour v2.
- [x] The top-level `View` returns `tea.View` and declares alt screen, colors, title, and active search cursor.
- [x] Blocking backend loading remains before `tea.NewProgram`; `Update` and `View` perform no I/O.
- [x] No goroutine mutates model state and the redesign adds no concurrency.
- N/A: there is no supersedable external async request, owned long operation, or resource beyond the Bubble Tea lifecycle.
- [x] Bubbles list, viewport, help, and filter-input update results/commands are retained.

## Input, focus, and navigation

- [x] `Ctrl+C` is global; ordinary text and bare `q` are not stolen from Bubbles input.
- [x] `Tab`/`Shift+Tab` move through a fixed feed/read focus order.
- [x] Wide/medium keep the selected feed row visible with a quieter inactive surface while reading is focused.
- [x] Compact focus changes the visible full-width mode; `Esc` from reading returns to the feed.
- [x] `Enter` applies active search; routine browsing has no hidden Enter action.
- [x] Escape follows search cancel/clear, then compact read-to-feed; it never unpredictably quits.
- [x] Footer help changes among `BROWSE`, `READ`, and `SEARCH`; compact read help keeps `Ctrl+C` visible.
- [x] Arrows and `j`/`k` handle primary navigation; page and end keys remain available in reading.
- N/A: there are no overlays or external processes in scope.
- [x] Mouse capture is disabled and the complete flow is keyboard accessible.

## Continuity and state preservation

- [x] Search preserves/restores selection by stable conversation identity when possible.
- [x] Resize and breakpoint changes preserve query, focus, selection, and bottom/relative reading position.
- [x] Applied filters still allow feed navigation and immediate reading refresh.
- [x] Compact feed/read transitions preserve the selected note and viewport.
- N/A: there is no streamed output, cancellation, retry, or partial-result state in this slice.

## Layout and responsive composition

- [x] `WindowSizeMsg` drives component dimensions.
- [x] Two-row masthead, optional one-row search strip, body, footer, surface padding, and gutter are budgeted exactly once.
- [x] Lip Gloss ANSI-aware width/height measurement backs representative geometry tests.
- [x] `150x40` and `109x33` use a recency journal, whitespace gutter, and raised reading sheet without a hard divider.
- [x] `90x30` uses deliberate feed/read modes rather than squeezed columns; `<72x18` uses an intentional resize screen.
- [x] The compact feed uses available space for an exact selected-outcome excerpt only when the visible entries fit.
- [x] The primary workflow never requires horizontal scrolling.
- [x] Narrative content wraps; feed titles truncate before source/turn/date rhythm is lost.
- [x] Tests assert exact `150x40`, `109x33`, `90x30`, and `60x12` canvases with the footer on-canvas.

## Visual hierarchy and aesthetics

- [x] The composition reads as field notes plus a reading sheet, not a database admin screen or transcript dump.
- [x] Two-line feed entries, aligned far-edge dates, selected marker/surface, authored whitespace, and timeline rhythm are consistent.
- [x] Semantic palette roles are centralized.
- [x] Vermilion focus/selection, quiet inactive selection, amber outcome/match, teal human voice, and sage status remain distinct.
- [x] Focus and state use words, shape, position, and surface as well as color.
- [x] Normal and muted text were legible in the inspected dark PTY.
- [x] No boxes surround the major regions; the remaining rules identify the outcome cue and message chronology.
- [x] The signature accent is scarce and semantic; the rejected lavender monotony is gone.
- [x] Common glyphs have no Nerd Font dependency.
- [x] There is no decorative animation.
- N/A: startup data loads before the TUI, so there is no transient in-app loading state.
- [x] Populated, no-match, too-small, focused/inactive, missing-summary, short-content, and long-content states are intentional.

## Search, async work, and streaming

- [x] Slash search is local Bubbles filtering and invokes no synthesis or network request.
- N/A: synchronous in-memory filtering needs no debounce, cancellation, stale request ID, or stream buffering.
- [x] Browse state has only a compact `/ search` affordance; the focused strip appears only during input.
- [x] Query, result count, input focus, and Escape recovery are visible; applied search collapses to masthead status.
- [x] No vague spinner, fabricated progress, cost, or telemetry is shown.
- [x] No-match preserves and names the query and exposes Escape recovery.

## Loading, empty, error, and recovery states

- [x] Populated startup teaches a useful first action.
- [x] No-match is distinct from an empty backend and includes the active query.
- N/A: there are no optional online features or degraded modes.
- [x] Startup backend failures name the failed load and preserve the cause on stderr.
- [x] Verbose application data is not dumped into an error screen.
- N/A: there are no destructive or irreversible actions in the slice.
- [x] Bubble Tea restored the alternate screen and cursor on private-PTY `Ctrl+C` exit/relaunch.

## Host and accessibility constraints

- [x] Real data was exercised in a private tmux server at `150x40`, `109x33`, and `90x30`.
- [x] Critical actions use arrows, Tab, Escape, Page keys, End, and `Ctrl+C`.
- [x] Native terminal selection remains available because mouse capture is disabled.
- [ ] Paste into the focused search input was not explicitly exercised.
- [x] No Nerd Font is assumed; Charm handles terminal color downsampling.
- [ ] Light-background and explicit `NO_COLOR` review were not performed.
- [x] Rapid blinking and decorative motion are absent; only the input cursor may blink.
- [x] Essential status and recovery text is linear and copyable.

## Verification and shipping gate

- [x] Changed Go files were formatted with host `gofmt`.
- [x] `GOMAXPROCS=2 /home/testycool/.local/bin/go vet ./...` passed with no diagnostics.
- [x] `GOMAXPROCS=2 /home/testycool/.local/bin/go test -p 1 ./...` passed.
- N/A: race was skipped because the visual reset changed no concurrent logic, as allowed by the task.
- [x] Private-PTY walkthroughs covered all three sizes, both compact modes, active/cleared search, selection continuity, Markdown, actual tail `END`, and `Ctrl+C`.
- [x] The rejected screenshot and raw private-PTY screen snapshots were inspected; no persistent generated visual artifact was retained.
- [x] A post-review subtraction removed duplicated browse position/scroll from the footer.
- [x] No debug stdout was added.
- [x] `aesthetic-ergonomic-scorecard.md` contains no zero; remaining 1s are explicit.
- [x] The visual result is ready for the user's judgment; this checklist is not acceptance evidence.

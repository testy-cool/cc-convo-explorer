# AgentConvos TUI product review checklist

Reviewed against real `agentconvos --context --json` data and the Bubble Tea TUI skill v1.1 checklist on 2026-08-03.

## Product and information architecture

- [x] The outcome and top tasks are explicit in `design-brief.md`.
- [x] The first screen identifies the project, result count/position, selected conversation, and available browse keys.
- [x] Selected content and the reading surface dominate supporting metadata.
- [x] Decorative labels, badges, logos, and rounded pane boxes were removed.
- [x] Goals, messages, selected content, and current work remain readable through detail wrapping/scrolling.
- [x] Truncated list titles have a predictable full-detail reveal beside them.

## Correctness and architecture

- [x] `go.mod` and imports use only Charm v2 modules.
- [x] The top-level `View` returns `tea.View` and declares alt screen, colors, title, and the search cursor.
- [x] The only blocking backend load occurs before `tea.NewProgram`; `Update` and `View` do no I/O.
- [x] No goroutine mutates model state.
- N/A: there is no supersedable external async request in this local browse/filter slice.
- N/A: there is no owned long operation to cancel.
- [x] Bubbles list, viewport, help, and text-input update results/commands are retained where applicable.
- N/A: the TUI owns no resources beyond the Bubble Tea program lifecycle.

## Input, focus, and navigation

- [x] Ctrl+C is handled globally; ordinary text and bare `q` are not stolen from input.
- [x] List/detail focus order is fixed and visible through `Tab` and `Shift+Tab`.
- [x] The selected row stays visible with a quieter inactive treatment while detail is focused.
- [x] `Enter` applies the active filter; routine browsing has no hidden Enter action.
- [x] `Esc` cancels/clears filtering and otherwise remains in the application.
- [x] Footer help changes among `BROWSE`, `READING`, and `FILTER` states.
- [x] Arrows and `j`/`k` are both exposed for moving/scrolling; page and end keys are exposed for detail.
- N/A: there are no overlays or external processes in scope.
- [x] Mouse capture is disabled; the complete workflow is keyboard accessible.

## Continuity and state preservation

- [x] Filtering preserves/restores selection by stable conversation identity when possible.
- [x] Resize preserves query, focus, selection, and bottom/relative detail position.
- [x] Applied filters still allow ordinary list navigation and immediate detail refresh.
- N/A: there is no streamed output, cancellation, retry, or partial result state in this slice.

## Layout and responsive composition

- [x] `WindowSizeMsg` drives all component dimensions.
- [x] Header, body, footer, pane widths, and the single separator are budgeted exactly once.
- [x] Lip Gloss cell-aware width/height measurement backs representative geometry tests.
- [x] `136x65`, `90x30`, and the `<72x18` too-small composition are intentional.
- [x] Compact mode preserves both browse context and the reading surface without horizontal scrolling.
- [x] Narrative content wraps; low-priority list metadata truncates or disappears first.
- [x] The detail region receives the flexible remainder rather than an equal-width split.
- [x] Tests assert exact `136x65`, `90x30`, and `60x12` canvases with footer/state on-canvas.

## Visual hierarchy and aesthetics

- [x] The result is calm, confident, warm, and purposeful rather than cyber-console or sterile dump.
- [x] Two-line row rhythm, stable metadata baselines, and one-cell grouping are consistent.
- [x] Semantic palette roles are centralized.
- [x] Accent focus, active/inactive selected bands, amber query/match, and sage scroll status are distinct.
- [x] Focus and scroll state also use words, row shape, and position rather than color alone.
- [x] Normal and muted text remained legible in the inspected dark terminal.
- [x] One separator communicates the pane boundary; nested borders are absent.
- [x] One main accent is supplemented only by subdued semantic roles.
- [x] Common glyphs are used; no Nerd Font is required.
- [x] There is no decorative animation.
- N/A: startup data is loaded before the TUI, so there is no transient in-app loading screen.
- [x] Populated, no-match, too-small, focused/unfocused, short-content, and long-content states are intentional.

## Search, async work, and streaming

- [x] Slash filtering is local Bubbles filtering and invokes no synthesis or network request.
- N/A: synchronous in-memory filtering needs no debounce, cancellation, or stale request ID.
- [x] Query, result count, filter focus, and recovery key remain visible.
- N/A: there is no stream to buffer.
- [x] No vague spinner or fabricated progress is shown.
- [x] The no-match state preserves the query, names it, and exposes Escape recovery.
- [x] No usage, latency, cost, or fabricated telemetry is displayed.

## Loading, empty, error, and recovery states

- [x] Populated startup teaches browse/filter/read keys in the footer.
- [x] No-match is distinct from an empty backend and includes the active query.
- N/A: there are no optional online features or degraded mode.
- [x] Startup backend failures name the failed load and preserve the cause on stderr.
- [x] Verbose application data is not dumped into an error screen.
- N/A: there are no destructive or irreversible actions in this slice.
- [x] Bubble Tea restores alternate-screen and cursor state on Ctrl+C exit in both PTY walkthroughs.

## Host and accessibility constraints

- [x] Real-data walkthroughs passed in private PTYs at `136x65` and `90x30`.
- [x] Critical actions use standard arrows, Tab, Escape, Page keys, and Ctrl+C.
- [x] Native terminal selection remains available because mouse capture is disabled.
- [ ] Paste into the focused filter was not explicitly exercised.
- [x] No Nerd Font is assumed; Charm handles terminal color downsampling.
- [ ] Explicit `NO_COLOR` and light-background visual review were not performed.
- [x] Rapid blinking and animation are absent; only the standard input cursor may blink.
- [x] Status and errors are represented as linear text, not only spatial/color cues.

## Verification and shipping gate

- [x] `/home/testycool/.local/bin/gofmt -w main.go main_test.go` exited 0.
- [x] `GOMAXPROCS=2 /home/testycool/.local/bin/go vet ./...` exited 0 with no diagnostics.
- [x] `GOMAXPROCS=2 /home/testycool/.local/bin/go test -p 1 ./...` passed.
- [x] `timeout 120s env GOMAXPROCS=2 /home/testycool/.local/bin/go test -race -p 1 ./...` passed.
- [x] Real backend walkthroughs covered both target sizes, browse/read/filter focus, selection restoration, page/end scrolling, and Ctrl+C exit.
- [x] Raw PTY screen output was inspected throughout the substantial visual change; no persistent screenshot artifact was retained.
- [x] No debug stdout was added.
- [x] `aesthetic-ergonomic-scorecard.md` contains no zero.
- [x] Score: `22/24`.
- [x] Remaining compromises are documented in the scorecard and final report.

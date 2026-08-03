# AgentConvos conversation journal — implementation plan

## Objective

Replace the rejected split-browser composition with a premium field-notes shell while preserving the proven real-data, selection, search, focus, viewport, and complete Markdown contracts.

## Ground truth and constraints

- Host Go only: `/home/testycool/.local/bin/go`; capped with `GOMAXPROCS=2` and `go test -p 1`.
- Module stack remains Bubble Tea `2.0.8`, Bubbles `2.1.1`, Lip Gloss `2.0.5`, and Glamour `2.0.1`, all `charm.land/.../v2`.
- Existing startup adapter continues to invoke `agentconvos --context --json` (or `AGENTCONVOS_BACKEND`) once before the TUI.
- The current real project payload has no populated `summary`/`slug`; the design must use exact opening/latest/outcome content and must not infer a recap.
- Scope remains browse/detail, focus, scrolling, and search only.
- No Docker, mouse capture, animation, background workers, handoff actions, launcher migration, packaging, or unrelated adapters.

## Implementation checkpoints

### 1. Specify the reset in tests

Add or revise focused tests before production edits, then observe the expected failures:

- `150x40` and `109x33` use a two-surface journal/reading composition with gutter whitespace, no hard separator, no generic detail heading, exact dimensions, and an on-canvas footer.
- `90x30` uses feed-only and read-only modes selected by focus; `Tab` and compact `Esc` preserve selection/query/scroll state.
- Browsing has no vacant input row; slash search reveals a full-width focused strip with result count and Escape language.
- The list delegate declares two rows, fills its assigned width when selected, aligns metadata/date, and distinguishes focused/inactive selection by both rail and surface.
- The reader exposes a wrapping title, honest exact latest-outcome excerpt, restrained metadata, and speaker-led timeline labels.
- Missing summaries and missing metadata do not generate fake or blank sections; duplicate first/latest-user content remains suppressed.
- Long Markdown remains rendered, complete, wrapped, and scrollable to a unique tail marker.

### 2. Recompose model geometry

- Extend `paneLayout` with a compact single-pane flag, authored masthead/search/footer heights, feed width, gutter width, and reading width.
- Use a `90x30`-appropriate breakpoint (chosen from measured content, not device labels) that switches the body to one major region.
- Keep selection identity, list filtering state, viewport offset, and component ownership unchanged across resize.
- In compact mode, derive visible region from explicit `paneFocus`; `Tab` toggles the region and `Esc` returns read to feed after temporary search state is cleared.

### 3. Redesign semantic presentation

- Replace lavender/plum tokens with graphite canvas/feed, warm paper/raised surfaces, ivory/taupe type, scarce vermilion signature, teal question, ochre answer, and sage state.
- Replace the vertical separator and bordered-pane language with a two/three-cell gutter and layered surfaces.
- Make the feed delegate two lines: timeline marker + concise humanized title, then rail + stable source/turn/date metadata.
- Compose a two-line masthead with publication identity, project, position/count, focus, search affordance, and applied-query state.
- Compose the footer from Bubbles key bindings into two calm groups plus a right-aligned focus/position/scroll state.

### 4. Build the reading sheet

- Replace generic pane headings and uppercase document sections with a hero and editorial message sequence.
- Hero order: note eyebrow/position, strong wrapping title, metadata band, **Latest outcome** exact first meaningful paragraph from the latest agent message.
- Timeline order: `You opened with` or `Task opened`; `You asked next` only when present and distinct; `Agent answered` with full latest-agent Markdown.
- Continue using Glamour v2 for all message bodies. Preserve source content, soft wrap to the calculated reading measure, and allow scrolling to the true tail.

### 5. Make search transient

- Retain the existing Bubbles list filter/input state and selection-anchor mechanics.
- Hide the input while browsing. On `/`, expose the deliberate search strip beneath the masthead and route ordinary keys exclusively to the component.
- On Enter, collapse to compact applied-query status. On Esc, cancel or clear before any compact-mode recovery.
- Keep no-match recovery inside the feed rather than filling the reader with fabricated content.

### 6. Visual review and subtraction

- Build once after green tests and drive real backend data in private PTYs at `150x40`, `109x33`, and `90x30` (feed, read, search, filtered, and tail states).
- Capture and inspect the actual ANSI screens as visual artifacts.
- Remove at least one element that competes with the selected title/outcome after the first review. Candidate removals are redundant focus prose, duplicated position labels, or an extra rule—not content required by the contract.
- Repeat only the focused test/build needed for the refinement, then perform the final capped gates.

## Model and key routing

- Canonical state remains `contextPayload`, Bubbles `list.Model`, `viewport.Model`, `help.Model`, `paneFocus`, dimensions, and stable filter-selection anchor.
- `Ctrl+C` quits globally.
- `/` enters search outside text entry; input consumes ordinary text/paste.
- `Tab`/`Shift+Tab` switch feed/read focus at every width. At compact width this also switches the visible screen.
- Feed focus sends arrows/`j`/`k` to Bubbles list. Read focus sends arrows/`j`/`k`, pages, and limits to Bubbles viewport.
- `Esc` ladder: cancel/clear active search, then return compact read to feed, otherwise stay in the app.

## Verification gates

Run serially, one command at a time:

```text
gofmt changed Go files
GOMAXPROCS=2 /home/testycool/.local/bin/go vet ./...
GOMAXPROCS=2 /home/testycool/.local/bin/go test -p 1 ./...
GOMAXPROCS=2 /home/testycool/.local/bin/go build -o bin/agentconvos-tui .
```

Skip race because the visual reset adds no concurrent logic. Then perform real-data PTY walkthroughs at the three target sizes, covering navigation, focus, transient search/clear, selection continuity, compact mode transition, Markdown rendering, tail reachability, and Ctrl+C.

Before committing: complete the skill review checklist and aesthetic/ergonomic scorecard honestly; inspect recent commit convention, status, and staged diff. Create one effect-oriented commit and do not amend or push.

## Acceptance

- The shell reads as a conversation journal and warm reading sheet, not the rejected data browser.
- Purpose and latest outcome are the first strong reading anchors.
- Recency feed, speaker timeline, search treatment, authored chrome, and palette are materially different from the rejected artifact.
- Real data and all pre-existing interaction/content guarantees remain intact.
- Supported canvases are exact and visually inspected, not only string-tested.
- The result is presented as ready for the user's visual judgment, never defended by a numeric score.

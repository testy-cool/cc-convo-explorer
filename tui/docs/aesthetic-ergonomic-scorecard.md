# AgentConvos conversation-journal aesthetic and ergonomic scorecard

Reviewed on 2026-08-04 with six real current-project conversations and private-PTY snapshots at `150x40`, `109x33`, and `90x30`. This is an internal completeness audit, not a claim of visual acceptance; the user's judgment remains the gate.

## Visual quality

| Criterion | 0–2 | Evidence / issue |
|---|---:|---|
| First-glance hierarchy makes context, selection, and current action obvious | 2 | Field-notes masthead establishes project/count/focus; full-width selected feed row leads directly to a wrapping title and exact latest outcome. |
| Spacing, alignment, and density form a consistent rhythm | 2 | Two-line feed records, far-edge dates, 2/3-cell gutter, warm reading measure, outcome breathing room, and speaker timeline held across target sizes. |
| Focus, selection, inactive selection, match, and activity are distinct | 2 | Marker plus full-width ember surface handles selection, a quieter warm surface handles inactive selection, vermilion identifies focus/search, and query/status roles remain separate. |
| Color is restrained, semantic, legible, and not the only carrier of meaning | 2 | Graphite/ink and warm ivory dominate; scarce vermilion, teal human voice, ochre agent/outcome, and sage state reinforce explicit labels and shape. |
| Borders, glyphs, badges, and motion are purposeful rather than decorative | 2 | The hard pane divider and generic cards are gone; only chronology/outcome rules remain; no logo badge, animation, or Nerd Font dependency. |
| Narrow, medium, and wide compositions look intentional | 2 | `150x40` is spacious, `109x33` preserves a composed reader, and `90x30` becomes full-width feed/read modes with a useful compact outcome cue. |

Visual subtotal: **12/12**.

## Interaction quality

| Criterion | 0–2 | Evidence / issue |
|---|---:|---|
| Primary tasks have short, predictable paths | 2 | Launch/orient, arrows to select, Tab to read, page/end to tail, slash to search. |
| Focus order, Enter behavior, and Escape ladder are clear | 2 | Tab/Shift+Tab, contextual footer, Enter apply, search clear/cancel, compact read-to-feed, and Ctrl+C fallback are explicit. |
| Search, refresh, resize, and streaming preserve selection and context | 2 | Stable filter anchor and resize-position tests pass; compact transitions preserve state; streaming is outside this slice. |
| Loading, empty, error, cancel, retry, and recovery states are actionable | 1 | No-match and too-small recovery are strong, but startup backend failure remains concise pre-TUI stderr and retry means rerunning the command. |
| Keyboard use is complete; help makes less-common actions discoverable | 2 | Arrows/Vim alternatives, page/end, focus, transient search, clear, and quit are contextual; compact help was shortened to keep Ctrl+C visible. |
| Terminal, tmux/SSH, reduced-color, glyph, paste, and accessibility constraints are handled | 1 | Real tmux PTYs, standard glyphs, no mouse/animation, and textual states passed; explicit paste, light-background, and `NO_COLOR` review remain. |

Interaction subtotal: **10/12**.

## Shipping gate

Total: **22/24**. No category scored zero.

The score is deliberately not used to defend the visual design. Remaining user impact from scores of 1:

- A backend startup failure exits with an actionable cause but has no in-app retry.
- Focused search was exercised with ordinary typing, not paste; light-background and explicit `NO_COLOR` presentation were not reviewed.
- Bubbles fuzzy filtering spans full conversation fields, so a common term such as `green` can match more notes than their titles imply; query and result count stay visible.

## Required review evidence

- Automated dimensions/states: `60x12` too-small; `90x30`, `109x33`, and `150x40`; browse, read, search-active/applied, no-match, missing-summary, short `ALL`, long `TOP`/`END`, active/inactive selection, and resize continuity.
- First real-data snapshots: all three target sizes before refinement, plus search, navigation, compact read, and long-tail `END` states.
- Post-review snapshots: compact feed with `ON THIS NOTE`, compact read with visible `Ctrl+C`, active search without duplicated affordance, and final medium/wide composition.
- Keyboard walkthrough: `j` changed selection/detail; Tab moved focus/mode; slash opened Bubbles search; typing updated results; Escape cleared/restored; End reached the actual latest-agent tail; Ctrl+C exited and the rebuilt binary relaunched.
- Markdown evidence: automated tests cover headings, emphasis, links, lists, and fenced Go code without literal syntax; the real tail snapshot showed rendered list bullets and `END`.
- Visual artifacts: raw private-tmux screen snapshots were inspected in the execution transcript; the rejected PNG was inspected at original resolution; no persistent screenshot/VHS file was retained.
- Known compromise: no explicit paste/light/`NO_COLOR` pass and no in-app startup retry.

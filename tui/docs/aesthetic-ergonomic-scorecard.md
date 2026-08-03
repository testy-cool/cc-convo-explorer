# AgentConvos TUI aesthetic and ergonomic scorecard

Reviewed on 2026-08-04 with six real current-project conversations from Codex and Claude, including the exact `106x30` state reported by the user.

## Visual quality

| Criterion | 0–2 | Evidence / issue |
|---|---:|---|
| First-glance hierarchy makes context, selection, and current action obvious | 2 | Header shows project/count/position; full-width row and dominant detail show selection; footer names focus and scroll state. |
| Spacing, alignment, and density form a consistent rhythm | 2 | Wrapped three-cell list rows, adjacent metadata, two-cell reader insets, compact chrome, and one separator held across all reviewed sizes. |
| Focus, selection, inactive selection, match, and activity are distinct | 2 | Accent focus rail/title, strong selected band, subdued inactive band, amber query treatment, textual focus mode; no background activity exists in this slice. |
| Color is restrained, semantic, legible, and not the only carrier of meaning | 2 | One lilac accent plus subdued selection, amber match, sage status, and textual/glyph equivalents. |
| Borders, glyphs, badges, and motion are purposeful rather than decorative | 2 | Rounded boxes and logo badge were removed; one plain separator and focus rail remain; no animation or Nerd Font dependency. |
| Narrow, medium, and wide compositions look intentional | 2 | Exact `60x12` too-small, `90x30` compact, user-reported `106x30` medium, and `136x65` wide renderings were inspected/tested. |

Visual subtotal: **12/12**.

## Interaction quality

| Criterion | 0–2 | Evidence / issue |
|---|---:|---|
| Primary tasks have short, predictable paths | 2 | Launch/orient, arrows to select, Tab to read, page/end to tail, slash to filter. |
| Focus order, Enter behavior, and Escape ladder are clear | 2 | Tab/Shift+Tab, contextual footer, Enter apply, Escape clear/cancel, Ctrl+C exit. |
| Search, refresh, resize, and streaming preserve selection and context | 2 | Stable filter anchor and resize-position tests pass; streaming is not part of this slice. |
| Loading, empty, error, cancel, retry, and recovery states are actionable | 1 | No-match and too-small recovery are strong, but backend load errors remain pre-TUI stderr with no in-app retry. |
| Keyboard use is complete; help makes less-common actions discoverable | 2 | Arrows/Vim alternatives, page/end, focus, filter, clear, and quit are contextual and were exercised. |
| Terminal, tmux/SSH, reduced-color, glyph, paste, and accessibility constraints are handled | 1 | Private PTY, standard glyphs, no mouse/animation, and text labels passed; explicit paste, light-background, and `NO_COLOR` review remain. |

Interaction subtotal: **10/12**.

## Shipping gate

Total: **22/24**. No category scored zero.

Remaining user impact from scores of 1:

- A backend failure exits before the TUI with a concise cause; retry requires rerunning the command.
- The focused filter was tested with ordinary typing but not paste, light-background rendering, or explicit `NO_COLOR` mode.
- Bubbles fuzzy filtering spans all conversation fields, so very short queries can produce broader matches than literal substring search; the query and result count remain visible.

## Required review evidence

- Automated dimensions/states: `60x12` too-small; `90x30`, `106x30`, and `136x65` populated; browse, reading, filter, no-match, missing metadata, short `ALL`, long `TOP`/percentage/`END`, active/inactive selection, and resize continuity.
- Screenshot-matched walkthrough at `106x30`: navigated to conversation `5 / 6`, confirmed humanized `README green CLI`, adjacent metadata, inset detail header, rendered Markdown links/lists, and visible `TOP` state.
- Real keyboard walkthrough at `136x65`: five list moves to `6 / 6`, Tab and Shift+Tab focus, Markdown links/code/lists, long-detail tail, filtering/count/cursor, Escape restoration to `2 / 6`, Ctrl+C exit 0.
- Real keyboard walkthrough at `90x30`: list navigation, Tab focus, Page Down to `13%`, End to reply tail, filtering/count/cursor, Escape restoration to `2 / 6`, Ctrl+C exit 0.
- Final rebuilt-artifact smoke at `136x65`: real backend loaded six conversations, `j` selected `2 / 6`, short detail reported `ALL`, Ctrl+C exit 0.
- Visual evidence: raw private-PTY screen captures were inspected in the execution transcript; no screenshot/VHS file was retained.
- Known compromise: no explicit paste/light/`NO_COLOR` visual pass and no in-app startup retry.

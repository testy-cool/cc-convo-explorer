# AgentConvos inline picker — implementation specification

Status: proposed revision of the existing inline picker; visual and hierarchy pass only

## Outcome

Running `agentconvos` in a terminal should let a developer identify and open a
recent conversation without entering a full-screen application. Selection is
interactive; the result becomes ordinary, complete shell scrollback that the
next coding agent can read immediately.

The experience should feel:

```text
calm · precise · shell-native
```

It must not feel:

```text
dashboard-like · decorative · custom-widget-heavy
```

## Primary workflow

```text
current project
  → run agentconvos
  → scan recent conversations
  → optionally filter
  → select one
  → read its complete catch-up record in shell scrollback
  → continue using the shell
```

The picker must never enter the alternate screen. Cancelling returns to the
existing prompt without printing a detail record. Opening a conversation prints
the record once and returns control to the shell.

## Scope

This specification covers only the default inline picker launched by
`agentconvos` and `agentconvos pick`:

- recent-conversation selection;
- compact metadata shown while selecting;
- the selected conversation's catch-up document;
- terminal-width adaptation, color fallback, and keyboard behavior.

The explicit `agentconvos tui` full-screen browser remains unchanged.

## Default-driven implementation constraint

Use the existing Huh v2 `Select` and `Form` lifecycle. Huh owns filtering,
navigation, focus, terminal redraw, help behavior, cancellation, and selection.
Do not introduce a custom Bubble Tea model for this iteration.

Start from Huh's existing `ThemeBase` styles and override only these semantic
roles:

| Role | Treatment |
|---|---|
| Primary | Terminal-default or off-white foreground |
| Muted | Readable neutral gray for metadata and secondary help |
| Accent | One restrained cyan for the selection marker and active key names |

Lip Gloss may compose labels and selected-detail headings. Glamour continues to
render message Markdown. Huh applies one style to an entire option, so option
keys remain plain, uniformly styled text; do not mix title and metadata colors
inside one option and do not embed ANSI sequences in option keys because Huh's
filter must continue matching the underlying text reliably. Terminal font,
terminal background, window border, shadow, and outer window chrome are owned
by the user's terminal emulator and are not part of AgentConvos.

No new UI dependency is required.

## Data contract

The backend remains `agentconvos --context --json` for the current working
directory. The picker consumes the existing normalized fields:

- project path;
- conversation UUID;
- summary/recap;
- source agent;
- timestamp;
- turn count;
- model and effort when recorded;
- first user message;
- latest user message;
- latest agent message.

Apply the existing maximum of five conversations per source agent, then restore
global reverse-chronological order. The newest conversation is selected by
default.

Conversation titles keep the existing fallback order:

1. first meaningful summary line;
2. humanized slug;
3. first meaningful user message;
4. `Untitled conversation`.

Missing values are omitted. The UI must not invent a recap, model, effort,
message, or timestamp.

## Picker presentation

### Information hierarchy

1. `Recent conversations` and the current project establish context.
2. The selected conversation title dominates the picker.
3. Other titles remain easy to scan.
4. Source, date, and turn count are supporting metadata.
5. Key help is visible but quiet.

### Conversation rows

Use a compact one-line option by default:

```text
› Make AgentConvos shell-native · codex · 04 Aug 2026 · 306 turns
```

- The selection marker is `›` in the accent color, while Huh keeps the option
  text itself uniformly styled for reliable filtering.
- Selected and unselected options may use Huh's uniform selection-state styles;
  no mixed title/metadata treatment is required.
- Model and effort do not appear in the picker row; they belong in detail.
- There is no selected-row background, card, border, badge, or underline.
- Rows are compact. Do not add a blank line after every option.

This one-line fallback is intentional: it keeps plain option keys compatible
with Huh filtering and avoids fighting Huh's renderer. If a future revision
uses two-line rows, its Huh `Height` must be budgeted from the rendered
`lipgloss.Height` of the title, description, options, and help; Huh counts
rendered lines, not logical records.

Truncate the title before metadata. Preserve source, date, and turn count when
space permits. Use one date format everywhere in the picker: `02 Jan 2006`,
including the year.

### Header and help

The picker establishes the command and project without a banner:

```text
agentconvos / convo-explorer
Recent conversations
```

Use the current project's final path component for the compact project label.
The complete path remains available from the backend and must not be repeated
in every row.

The field description is reserved for the heading and contains no key help.
Expose actions only through Huh's help model and binding help text. Keep the
whole stock help line uniformly muted; do not color only `enter` and `esc`.
Use these action words:

```text
↑↓ move   / filter   enter open   esc cancel
```

Symbols, key names, and descriptions remain muted. Do not add a footer box.

### Interaction

- `↑` and `↓` move selection.
- `/` starts Huh's built-in filtering.
- `Enter` opens the selected conversation.
- `Esc` or `Ctrl+C` cancels the picker.
- Filtering retains Huh's default matching and editing behavior.
- No mouse support, animation, spinner, timer, or background refresh is added.

## Selected conversation document

After selection, print one short confirmation followed by the complete detail:

```text
Opened Make AgentConvos shell-native

convo-explorer
04 Aug 2026 · codex · gpt-5.6-sol · xhigh · 306 turns

Recap
Replaced the full-screen browser with a shell-native conversation picker.

First message
Let's build a better way to browse and open conversations.

Your latest message
Can't it be a beautiful interactive CLI?

Agent reply
<complete rendered reply>
```

Rules:

- The project label is the compact project name, not `Project <full path>`.
- Metadata order is date, source, model, effort, and turn count.
- Use `Recap`, not `Summary`, when recap text exists.
- Omit `Your latest message` when it normalizes to the same text as
  `First message`.
- Preserve the complete latest agent reply. Never truncate it.
- Render Markdown without code-block backgrounds or decorative margins.
- Wrap to the terminal width using ANSI-aware measurement.
- Omit the horizontal separator used by the current renderer.
- Section labels use primary bold text, not the accent color.
- Do not print an extra duplicate copy of the selected conversation.

## Responsive behavior

### Ordinary terminals: 72 columns and wider

- Use the compact one-line picker rows.
- Show at most ten visible options; let Huh scroll additional options.
- Wrap detail content to the available terminal width.

### Narrow terminals: 40–71 columns

- Keep the one-line option format.
- Truncate title before metadata.
- Allow detail headings and body content to wrap naturally.
- Keep selection, filtering, opening, and cancellation fully usable.

### Below 40 columns

Huh may use its existing minimum-width behavior. AgentConvos must not panic,
emit broken ANSI sequences, or enter the alternate screen.

### Color capability

- Respect `NO_COLOR` and `TERM=dumb`.
- In plain mode, hierarchy comes from order, indentation, and the `›` marker.
- Do not require truecolor, a Nerd Font, italics, or a particular terminal
  background.

## Empty and failure states

- No conversations: print `No conversations found for <project>.` and exit 0;
  retain the existing full project path in this empty-state message. Detail
  output uses only the compact project name.
- User cancellation: print no detail and exit 0.
- Backend failure: print the existing concise `agentconvos pick:` error to
  stderr and exit non-zero.
- Selector and Markdown-rendering errors preserve the current output stream;
  backend-loading errors remain on stderr.
- Selected record unavailable: print the existing unavailable error and exit
  non-zero.
- Markdown rendering failure: name the failed section and exit non-zero.

Do not add modal dialogs or retry UI.

## Performance contract

- Continue loading one current-project JSON payload before interaction.
- Do not parse additional transcripts while moving selection.
- Do not call an LLM, summary service, network service, or Docker process.
- Selection movement and filtering must remain local and perceptually instant.
- Do not add animation ticks or recurring refresh work.

## Explicit non-goals

- Rebuilding the picker as a bespoke Bubble Tea application.
- Changing the full-screen Textual or Bubble Tea browser.
- Adding previews, panes, cards, borders, badges, icons, gradients, or themes
  selectable at runtime.
- Changing recap generation, search ranking, transcript parsing, resume,
  handoff, or persistence.
- Reproducing terminal-emulator window chrome from the concept image.

## Acceptance criteria

1. `agentconvos` and `agentconvos pick` launch the same inline Huh picker.
2. The picker never emits alternate-screen enter/leave sequences.
3. Results are globally recency-sorted after the five-per-source cap.
4. The newest result is selected initially.
5. Available option metadata appears: title, source, date, and turn count when
   recorded.
6. Selection is visible without relying on color alone.
7. `/`, arrows, `Enter`, `Esc`, and `Ctrl+C` retain their declared behavior.
8. The selected detail includes available recap, first message, distinct latest
   user message, full latest agent reply, date, source, model, effort, turns,
   and compact project name.
9. Missing and duplicate sections are omitted rather than printed as `None` or
   repeated.
10. The complete agent reply remains present after Markdown rendering and
    terminal wrapping.
11. `NO_COLOR` and non-TTY output remain readable.
12. The visual system uses only primary, muted, and accent roles and adds no
    decorative container.
13. The real command completes from selection back to a usable shell prompt.

## Verification

Automated checks:

```bash
cd tui
go test ./...
go vet ./...
```

Required render assertions cover:

- populated picker output at 100 and 60 columns;
- long title truncation with metadata retained;
- five-per-source ordering;
- duplicate first/latest-user omission;
- missing recap/model/effort omission;
- full reply tail sentinel preservation;
- `NO_COLOR` output;
- Escape cancellation and absence of alternate-screen sequences.

Required live check:

```bash
agentconvos
```

Run it from this repository in a real terminal, move selection, filter, cancel,
run it again, open a conversation, confirm the full reply is present, and
confirm the shell prompt remains usable afterward.

## Implementation boundary

Expected files:

- `tui/cmd/agentconvos-pick/main.go`: Huh composition, labels, and theme roles;
- `tui/cmd/agentconvos-pick/main_test.go`: interaction and responsive labels;
- `tui/inlinepicker/picker.go`: selected-detail hierarchy, picker option labels,
  and picker date formatting;
- `tui/inlinepicker/picker_test.go`: complete detail and omission contracts.

No other production file should need to change.

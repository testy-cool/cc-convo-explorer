# agentconvos

Discover, query, and browse AI coding agent conversations. Works with Claude Code, Codex, Pi, Agy, and OpenCode.

Use as a **CLI** (`agentconvos --context --json`), a **Python library** (`from agentconvos import scan_projects`), or an **interactive TUI** (`agentconvos`).

<img src="assets/demo.svg" alt="agentconvos demo">

## Install

```bash
uv tool install "agentconvos[ai] @ git+https://github.com/testy-cool/agentconvos.git"
```

Without Gemini analysis: drop `[ai]`. Requires Python 3.12+.

## CLI

### Project context (the fast path)

```bash
agentconvos --last              # most recent conversation for cwd
agentconvos --last 3            # last 3
agentconvos --context           # last 5 with summaries
agentconvos --context --json    # structured, for piping to other tools
```

### Agentic recall

```bash
agentconvos recall "Where did we decide how scraper fallbacks should work?"
```

`recall` searches the archive iteratively, opens only the promising conversation
turns, reconciles conflicting evidence, and answers with source, date, session,
turn, and project-path citations. The retrieval worker runs ephemerally in an
isolated workspace, treats transcript instructions as untrusted data, and keeps
its model and retrieval plumbing out of the caller-facing interface. It requires
an installed and authenticated Codex CLI.

### Search

```bash
agentconvos --search "auth middleware"
agentconvos --search 'auth "request id"'     # all words + an exact phrase
agentconvos --search "auth" --source claude --json
```

Search is case-insensitive. Separate words use AND matching across a conversation,
quoted text stays together as an exact phrase, and the strongest matches appear first.
CLI results come from a persistent turn-level SQLite index, so each hit includes the
original role and turn number without reparsing every transcript. Existing indexes
receive a one-time turn backfill on the first search; a large archive can take several
minutes once, after which only new or changed conversations are reindexed.

### Fast interactive find

```bash
agentconvos --find                    # open the fuzzy conversation picker
agentconvos -f "auth reqid"           # start with a fuzzy query
agentconvos -f --source codex         # limit the picker to one agent
```

This skips the Textual TUI and opens a lightweight `fzf` picker instead. It searches
cached session IDs, titles, paths, branches, first prompts, and saved summaries as you
type. The highlighted conversation is parsed lazily in the preview pane, so launching
the picker stays fast even with a large history. Press Enter to print the exact session
ID plus ready-to-copy `--show` and `--resume` commands. Requires `fzf` on `PATH`.

### List and filter

```bash
agentconvos --list
agentconvos --list --source codex --after 2026-05-01 --json
agentconvos --list --json | jq '.projects[].conversations[].summary'
```

### Resume and handoff

```bash
agentconvos --resume                   # latest resumable session for cwd
agentconvos --resume select            # choose a session for cwd
agentconvos --resume <id>              # resume a specific session
agentconvos --resume <id> --yolo       # explicitly bypass the target agent's permission prompts
agentconvos --handoff                  # export context, start new session
agentconvos --handoff select           # pick from list
agentconvos --handoff codex            # latest Codex conversation
agentconvos --convo agy --handoff codex --yolo  # hand off latest Agy conversation into Codex with codex --yolo
agentconvos --convo agy --handoff claude --yolo # hand off latest Agy conversation into Claude with no prompts
agentconvos --handoff --handoff-agent codex   # hand off latest conversation into Codex
agentconvos --handoff --yolo           # hand off latest conversation to the same agent with no prompts
```

Resume and handoff preserve each agent's normal permission behavior by default.
`--yolo` is the explicit opt-in for agents that expose a no-prompt mode. Native
resume is available for Claude Code, Codex, Pi, Agy, and OpenCode conversations.

### Export

```bash
agentconvos --concat <id>              # markdown export
agentconvos --concat <id> --detail tools    # include tool call summaries
agentconvos --concat <id> --detail full     # include everything
agentconvos --turns <id> --json        # normalized user/assistant turns on stdout
```

`--turns` defaults to `--detail text`, which excludes tool calls, tool results,
reasoning blocks, and agent-injected bootstrap/command metadata. Use
`--detail tools`, `results`, `thinking`, or `full` for a targeted deeper export.

### Analyze with Gemini

Requires `GEMINI_API_KEY` env var or `.env` file. Get a key at [aistudio.google.com](https://aistudio.google.com/apikey).

```bash
agentconvos --analyze <id>
agentconvos --analyze <id1> <id2> --model gemini-3.1-pro-preview
agentconvos --analyze <id> --prompt "What tools were used most?"
```

### JSON output

`--json` works with `--list`, `--search`, `--last`, `--context`, and `--turns`.
Transcript output includes normalized indexed turns plus source, path, UUID, cwd,
size, and modification metadata.

## Library API

```python
from agentconvos import scan_projects, parse_jsonl, search, get_meta, get_stats

# Discover and filter
projects = scan_projects(source="claude", after="2026-05-01")

# Parse into normalized turns
turns = parse_jsonl(projects[0].conversations[0].path)

# Search across all sessions
hits = search([c.path for p in projects for c in p.conversations], "auth")

# Token and cost stats
stats = get_stats(projects[0].conversations[0].path)
```

## TUI

```bash
agentconvos
```

Interactive tree grouped by agent (Claude Code, Codex, Pi, Agy, OpenCode) with search, multi-select, preview, export, and Gemini analysis.

The history tree renders from cached metadata immediately. A persistent SQLite
full-text index updates in the background, with progress shown in the lower-right
badge; only new or changed transcripts are parsed on later starts. Search results
appear live while a first-time index is still filling.

The search box is focused at launch and searches titles, prompts, paths, branches,
summaries, and full conversation text. Matching context appears directly in the
tree; press Enter to open the first match. Conversation previews parse lazily and
highlight the matching turns. Resume asks for confirmation with the agent, working
directory, full session ID, and command.

| Key | Action |
|-----|--------|
| `/` | Focus full-text search |
| `S` | Toggle select |
| `R` | Review and resume session |
| `H` | Handoff to new session |
| `E` | Export markdown |
| `A` | Analyze with Gemini |
| `Tab` | Switch panels |
| `Q` | Quit |

## File locations

| What | Where |
|------|-------|
| Claude Code logs | `~/.claude/projects/{project}/*.jsonl` |
| Codex logs | `~/.codex/sessions/*.jsonl`, `~/.codex/conversations/*.json` |
| Pi logs | `~/.pi/agent/sessions/**/*.jsonl` |
| Agy logs | `~/.gemini/antigravity-cli/history.jsonl`, `~/.gemini/antigravity-cli/conversations/*.db` |
| OpenCode sessions | `~/.local/share/opencode/opencode.db` |
| Full-text search index | `~/.claude/convo-explorer/search-index.sqlite3` |
| Summaries | `~/.claude/convo-explorer/summaries/` |
| Analyses | `~/.claude/convo-explorer/analyses/` |

## License

MIT

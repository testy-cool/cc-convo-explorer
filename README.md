# agentconvos

Discover, query, and browse AI coding agent conversations. Works with Claude Code, Codex, Pi, and Agy.

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

### Search

```bash
agentconvos --search "auth middleware"
agentconvos --search 'auth "request id"'     # all words + an exact phrase
agentconvos --search "auth" --source claude --json
```

Search is case-insensitive. Separate words use AND matching across a conversation,
quoted text stays together as an exact phrase, and the strongest matches appear first.

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
agentconvos --handoff                  # export context, start new session
agentconvos --handoff select           # pick from list
agentconvos --handoff codex            # latest Codex conversation
agentconvos --convo agy --handoff codex --yolo  # hand off latest Agy conversation into Codex with codex --yolo
agentconvos --convo agy --handoff claude --yolo # hand off latest Agy conversation into Claude with no prompts
agentconvos --handoff --handoff-agent codex   # hand off latest conversation into Codex
agentconvos --handoff --yolo           # hand off latest conversation to the same agent with no prompts
```

### Export

```bash
agentconvos --concat <id>              # markdown export
agentconvos --concat <id> --detail tools    # include tool call summaries
agentconvos --concat <id> --detail full     # include everything
```

### Analyze with Gemini

Requires `GEMINI_API_KEY` env var or `.env` file. Get a key at [aistudio.google.com](https://aistudio.google.com/apikey).

```bash
agentconvos --analyze <id>
agentconvos --analyze <id1> <id2> --model gemini-3.1-pro-preview
agentconvos --analyze <id> --prompt "What tools were used most?"
```

### JSON output

`--json` works with `--list`, `--search`, `--last`, and `--context`. Output includes session summaries, token estimates, file paths, and UUIDs.

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

Interactive tree grouped by agent (Claude Code, Codex, Pi, Agy) with search, multi-select, preview, export, and Gemini analysis.

Search runs across full conversation text as you type. Matching terms and their
surrounding context appear directly in the tree; press Enter to open the first
match. Search previews center and highlight matching turns. Resume asks for
confirmation with the agent, working directory, full session ID, and command.

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
| Summaries | `~/.claude/convo-explorer/summaries/` |
| Analyses | `~/.claude/convo-explorer/analyses/` |

## License

MIT

---
name: agentconvos
description: Recover context from past AI coding sessions on this machine (Claude Code, Codex, Pi, Agy, OpenCode, Clihow). Use at the start of work in an unfamiliar repo, and whenever the user refers to earlier work you cannot see - "what were we doing here", "what did we decide about X", "the thing we fixed yesterday", "we already tried that", "remember when", "why is this written this way", "find that conversation", "resume where we left off". Also for handing a session to another agent.
---

# agentconvos

Your context window starts empty every session. The user's does not. This
reads the conversation archive already on their disk so you can answer from
what was actually said instead of guessing or asking them to repeat it.

Git tells you what changed. This tells you what was discussed and why, which
is usually the part that was never written down.

## Pick the command by what you need

| You need | Command | Cost |
|---|---|---|
| What happened in this directory | `agentconvos --context` | free, instant |
| A conversation containing some words | `agentconvos --search "terms"` | free, indexed |
| A decision and its reasoning, across sessions | `agentconvos recall "question"` | a model call |
| The full text of one conversation | `agentconvos --turns <id> --json` | free |
| To continue a session in its own agent | `agentconvos --resume <id>` | starts a CLI |

Work down that list. `--context` answers most catch-up questions on its own,
and `--search` answers most of the rest. Reach for `recall` when the answer is
spread over several sessions or the user asks *why* something was decided.

## Catching up on a directory

```bash
agentconvos --context          # last 5 sessions per agent, with catch-up detail
agentconvos --context --json   # same, machine-readable
agentconvos --last 3           # last 3 conversations, compact
```

`--context` reports on the **current working directory**, so run it from the
repo you are asking about. It gives you, per conversation: date, turn count,
model, effort, the first thing the user asked, their latest message, the
latest agent reply, and a cached summary when one exists.

Read it before asking the user to re-explain the project. If it comes back
empty, the work simply was not done in this directory.

## Finding a conversation

```bash
agentconvos --search "auth middleware"          # all words, anywhere in a conversation
agentconvos --search 'auth "request id"'        # quoted text stays an exact phrase
agentconvos --search "auth" --source codex --json
```

Search is case-insensitive and ranked, and runs against a local SQLite index,
so it is fast even over thousands of sessions. JSON hits carry `uuid`,
`source`, `timestamp`, `cwd`, `file`, `turn_index`, `role`, and `snippet` -
enough to cite a specific turn without opening the transcript.

The very first search on a new machine may spend several minutes building the
index. That happens once.

## Asking a question the archive has to answer

```bash
agentconvos recall "Where did we decide how scraper fallbacks should work?"
agentconvos recall --backend agy "Why did we drop the Redis cache?"
```

`recall` searches iteratively, opens only promising turns, and answers with
source, date, session id, turn numbers, and project paths. Use it when a
plain search will not do: the answer spans sessions, or the user wants the
reasoning rather than the message.

It costs a real model call and needs an authenticated Codex CLI, or
`--backend agy` for the local AGY bridge. Try `--search` first.

## Reading a conversation without drowning in it

```bash
agentconvos --turns <id> --json                  # normalized user/assistant turns
agentconvos --turns <id> --json --detail full    # plus tool calls and results
agentconvos --concat <id>                        # markdown export
```

`--turns` defaults to text only: no tool calls, no tool results, no reasoning
blocks, no harness bootstrap noise. That default exists so you can read a
conversation without spending your context on machine chatter. Only ask for
`--detail tools` or `full` when the tool activity is the thing you need.

Sessions can be hundreds of thousands of tokens. Check `estimated_tokens` in
`--context --json` before pulling a whole transcript into your context.

## Continuing or handing off work

```bash
agentconvos --resume <id> --dry-run   # print the command, run nothing
agentconvos --resume <id>             # continue in the agent that created it
agentconvos --handoff codex           # move this directory's context to Codex
```

Use `--dry-run` first and show the user the command. Resume replaces the
session they are in; that is their call, not yours.

## Sending data off the machine

Everything above is local. Three things are not:

- `agentconvos --analyze` sends conversation text to Gemini
- `agentconvos --summarize` sends conversation text to Gemini
- `agentconvos recall` sends transcript excerpts to its retrieval worker

Conversation archives hold whatever the user has ever pasted into an agent:
credentials, customer data, unreleased work. Do not run these on someone's
archive without telling them what leaves the machine.

## Identifiers

A conversation id is a UUID, and a prefix works. Anywhere an id is accepted a
file path works too. `--source` narrows to one agent: `claude`, `codex`, `pi`,
`agy`, `opencode`, `clihow`.

## When there is nothing to find

An empty result is an answer. Say the archive has no record of it rather than
filling the gap with a plausible story - the user can tell the difference, and
inventing history is worse than admitting the search came up empty.

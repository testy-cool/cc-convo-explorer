"""Local, deterministic language-pattern reports for agent replies."""

from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .ngrams import assistant_reply_text
from .ngrams import phrases as lexical_phrases


@dataclass(frozen=True)
class Variant:
    label: str
    regex: str
    minimum_word_offset: int = 0
    first_match_only: bool = False


@dataclass(frozen=True)
class Pattern:
    key: str
    name: str
    description: str
    variants: tuple[Variant, ...]
    kind: str
    minimum_sessions: int = 1


@dataclass(frozen=True)
class SessionReply:
    session_id: str
    project: str
    text: str
    date: str = ""


@dataclass(frozen=True)
class Example:
    session_id: str
    project: str
    date: str
    before: str
    match: str
    after: str


@dataclass(frozen=True)
class PatternSummary:
    key: str
    name: str
    description: str
    kind: str
    phrases: tuple[str, ...]
    occurrences: int
    sessions: int
    projects: int
    examples: tuple[Example, ...]
    instances: tuple[Example, ...]

    def public_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "phrases": list(self.phrases),
            "occurrences": self.occurrences,
            "sessions": self.sessions,
            "projects": self.projects,
            "examples": [asdict(example) for example in self.examples],
            "instances": [asdict(example) for example in self.instances],
        }


@dataclass(frozen=True)
class HabitReport:
    source: str
    generated: str
    sessions: int
    patterns: tuple[PatternSummary, ...]

    def public_dict(self) -> dict:
        return {
            "source": self.source,
            "generated": self.generated,
            "sessions": self.sessions,
            "pattern_count": len(self.patterns),
            "match_count": sum(pattern.occurrences for pattern in self.patterns),
            "patterns": [pattern.public_dict() for pattern in self.patterns],
        }


def _v(label: str, regex: str | None = None) -> Variant:
    return Variant(label, regex or rf"\b{re.escape(label)}\b")


def _s(
    label: str,
    regex: str,
    *,
    minimum_word_offset: int = 0,
    first_match_only: bool = False,
) -> Variant:
    return Variant(label, regex, minimum_word_offset, first_match_only)


SEED_PATTERNS = (
    Pattern(
        "verification",
        "Verification preamble",
        "Announces a check before acting.",
        tuple(_v(item) for item in ("let me check", "let me verify", "let me look", "let me find", "let me confirm")),
        "Seed pattern",
    ),
    Pattern(
        "prospective",
        "Prospective action",
        "States the next action before taking it.",
        (_v("I'll start by", r"\bI['’]ll start by\b"),),
        "Seed pattern",
    ),
    Pattern(
        "anti_guessing",
        "Anti-guessing contrast",
        "Explicitly prefers inspection over inference.",
        (_v("rather than guess"),),
        "Seed pattern",
    ),
    Pattern(
        "handback",
        "Control handback",
        "Returns the next decision to the user.",
        tuple(_v(item) for item in ("want me to", "say the word", "if you want")),
        "Seed pattern",
    ),
    Pattern(
        "repair",
        "Repair ritual",
        "Begins a correction by recognizing the user's objection.",
        (_v("you're right", r"\byou['’]re right\b"),),
        "Seed pattern",
    ),
    Pattern(
        "attention",
        "Attention directing",
        "Marks information as worth the reader's attention.",
        tuple(_v(item) for item in ("worth knowing", "worth flagging", "worth noting", "worth saying", "worth naming")),
        "Seed pattern",
    ),
    Pattern(
        "inventory",
        "Verbal inventory",
        "Announces the size of a list before giving it.",
        tuple(_v(item) for item in ("two things", "one thing", "loose ends")),
        "Seed pattern",
    ),
    Pattern(
        "negative_audit",
        "Negative audit ledger",
        "Establishes scope with explicit absences and non-actions.",
        tuple(_v(item) for item in ("not touched", "does not exist", "did not run", "could not see", "did not read")),
        "Seed pattern",
    ),
    Pattern(
        "reversibility",
        "Reversibility reassurance",
        "Frames a change as recoverable or currently costless.",
        tuple(_v(item) for item in ("nothing is lost", "costs nothing", "loses nothing")),
        "Seed pattern",
    ),
    Pattern(
        "artifact_witness",
        "Artifacts as witnesses",
        "Makes technical artifacts grammatical authorities or observers.",
        tuple(_v(item) for item in ("the skill says", "the rule says", "the screenshot shows", "tests pass", "checks pass")),
        "Seed pattern",
    ),
    Pattern(
        "demonstrative",
        "Demonstrative verdict",
        "Compresses a preceding finding into a short this or that verdict.",
        (_v("this is the"), _v("that's the", r"\bthat['’]s the\b"), _v("that is the")),
        "Seed pattern",
    ),
    Pattern(
        "state",
        "State anchoring",
        "Lexically locates a claim in the current state.",
        tuple(_v(item) for item in ("still open", "still exists", "already exists", "right now", "actually is")),
        "Seed pattern",
    ),
    Pattern(
        "causal",
        "Causal explanation",
        "Connects a finding to an explicit reason.",
        tuple(_v(item) for item in ("which is why", "because this", "because the", "since this", "since the")),
        "Seed pattern",
    ),
)


STRUCTURAL_PATTERNS = (
    Pattern("negative_parallelism", "Negative parallelism", "Repeats a negation to create a compact ledger of absences.", (_s("No X, no Y", r"\b(?:no|not|never|without)\s+[^,.;:\n]{1,60},\s*(?:and\s+|or\s+)?(?:no|not|never|without)\s+[^,.;:\n]{1,60}"),), "Detected structure", 10),
    Pattern("contrastive_correction", "Contrastive correction", "Rejects one reading and replaces it with another.", (_s("Not X, but Y", r"\bnot\s+[^.!?\n]{1,100}?\b(?:but|instead|rather)\b"),), "Detected structure", 10),
    Pattern("concession_pivot", "Concession pivot", "Acknowledges one condition before pivoting to a competing fact.", (_s("Although X, still Y", r"\b(?:although|even though|while)\b[^.!?\n]{1,160}\b(?:but|still|yet)\b|\b(?:that said|even so)\b"),), "Detected structure", 10),
    Pattern("replacement_contrast", "Replacement contrast", "Frames an action as a deliberate replacement for another.", (_s("Rather than / instead of", r"\b(?:rather than|instead of)\b"),), "Detected structure", 10),
    Pattern("diagnostic_frame", "Diagnostic frame", "Introduces a finding as the problem, issue, catch, or risk.", (_s("The problem is", r"\b(?:the\s+)?(?:problem|issue|catch|risk)\s+is\b"),), "Detected structure", 10),
    Pattern("recommendation_frame", "Explicit recommendation", "Labels advice as a recommendation rather than leaving it implicit.", (_s("My recommendation", r"\b(?:my\s+recommendation|I\s+recommend|the\s+recommendation\s+is)\b"),), "Detected structure", 10),
    Pattern("summary_frame", "Summary frame", "Signals a compressed answer or state summary.", (_s("Short answer / bottom line", r"\b(?:the\s+short\s+answer|short\s+version|bottom\s+line|where\s+things\s+stand|the\s+full\s+picture)\b"),), "Detected structure", 10),
    Pattern("priority_frame", "Priority frame", "Names one point as the main, key, important, only, or real one.", (_s("The key point", r"\bthe\s+(?:only\s+thing|main\s+(?:point|thing)|important\s+(?:part|thing)|key\s+(?:point|difference|thing)|real\s+(?:problem|issue|question))\b"),), "Detected structure", 10),
    Pattern("categorical_absence", "Categorical absence", "Uses a direct negative assertion to delimit what exists or happened.", (_s("There is no / did not", r"\b(?:there\s+(?:is|are)\s+no|it\s+does\s+not|I\s+did\s+not|I\s+could\s+not)\b"),), "Detected structure", 10),
    Pattern("technical_agency", "Technical artifacts as actors", "Makes an artifact the grammatical source of a claim.", (_s("The artifact says / shows", r"\b(?:the\s+)?(?:tests?|traces?|logs?|files?|database|index|service|server|client|tool|skill|screenshot|report|output|response|API)\s+(?:says?|shows?|reports?|confirms?|expects?|rejects?|accepts?|records?|returns?|contains?)\b"),), "Detected structure", 10),
    Pattern("exactness_emphasis", "Exactness emphasis", "Strengthens a claim with exactness or byte-level identity.", (_s("Exactly / byte for byte", r"\b(?:exactly\s+(?:the|what|as|where|how)|is\s+exactly|byte[- ]for[- ]byte|byte[- ]identical)\b"),), "Detected structure", 10),
    Pattern("temporal_completion", "Completion handoff", "Defers the next step to a future completion event.", (_s("When it lands / finishes", r"\b(?:when\s+it\s+(?:lands|finishes|completes)|as\s+soon\s+as)\b"),), "Detected structure", 10),
    Pattern("alternative_offer", "Alternative offer", "Offers another path or explicitly hands back preference.", (_s("If you'd rather", r"\b(?:if\s+you['’]d\s+rather|do\s+you\s+want|whenever\s+you\s+want)\b"),), "Detected structure", 10),
    Pattern("explicit_uncertainty", "Explicit uncertainty", "Names an evidentiary limit instead of filling it with inference.", (_s("I don't know / cannot determine", r"\b(?:I\s+(?:don['’]t\s+know|can['’]t\s+tell|cannot\s+tell)|cannot\s+determine|not\s+enough\s+evidence)\b"),), "Detected structure", 10),
    Pattern("self_correction", "Visible self-correction", "Surfaces a nearly-made or already-made wrong claim.", (_s("I almost said / I was wrong", r"\b(?:I\s+(?:almost|nearly)\s+(?:said|reported|called|wrote)|I\s+was\s+wrong)\b"),), "Detected structure", 10),
    Pattern("em_dash_chain", "Em-dash clause chain", "Links multiple asides or qualifications with repeated em dashes.", (_s("X — Y — Z", r"—[^.!?\n]{1,160}—"),), "Detected structure", 10),
    Pattern("colon_diagnosis", "Colon diagnosis", "Names a diagnostic category and delivers its conclusion after a colon.", (_s("The problem:", r"\b(?:problem|reason|issue|catch|difference|point|answer|result)(?:\s+(?:is|was))?\s*:"),), "Detected structure", 10),
    Pattern("comparative_pair", "Paired comparison", "Uses a compact repeated-preposition comparison.", (_s("End to end / side by side", r"\b(?:end[- ]to[- ]end|side[- ]by[- ]side|byte[- ]for[- ]byte)\b"),), "Detected structure", 10),
    Pattern("fallback_frame", "Fallback framing", "Describes behavior in terms of a fallback path.", (_s("Falls back to", r"\b(?:falls?\s+back\s+to|fallback)\b"),), "Detected structure", 10),
    Pattern("vague_demonstrative", "Demonstrative compression", "Uses this or that as the subject of a verdict without repeating its referent.", (_s("This means / that leaves", r"\b(?:this|that|these|those)\s+(?:is|are|means?|shows?|leaves?|makes?)\b"),), "Detected structure", 10),
    Pattern("honesty_frame", "Honesty framing", "Marks an answer, limitation, or assessment as honest or candid.", (_s("Honest / honestly", r"\b(?:honest|honestly)\b"),), "Detected structure", 10),
    Pattern("decision_ownership", "Decision-ownership handoff", "Explicitly assigns a choice or unresolved question to the user.", (_s("Yours to decide / your call", r"\b(?:(?:all|both)\s+(?:are\s+)?yours\s+to\s+(?:decide|choose)|yours\s+to\s+(?:decide|choose)|your\s+(?:decision|call|choice)|the\s+decision\s+is\s+yours|up\s+to\s+you\s+(?:to|whether|how))\b"),), "Detected structure", 10),
    Pattern("remaining_side_handoff", "Remaining-side handoff", "Assigns the other or remaining side of a split problem to the user.", (_s("The other is yours", r"\b(?:the\s+)?(?:other|remaining|rest)\b[^.!?\n]{0,100}\b(?:is|are)?\s*(?:all\s+)?(?:yours|up\s+to\s+you|your\s+call)\b"),), "Detected structure", 2),
    Pattern("staged_disclosure", "Staged disclosure", "Introduces a first stage before revealing a second or subsequent stage.", (_s("First ... then / second", r"\bfirst\b(?=[\s\S]{0,500}\b(?:second|then)\b)"),), "Detected structure", 10),
    Pattern("delayed_verdict", "Delayed verdict", "The first explicit answer or recommendation marker appears after at least 60 words.", (_s("Verdict marker after 60 words", r"\b(?:the\s+(?:short\s+)?answer\s+is|bottom\s+line|my\s+recommendation(?:\s+is)?|the\s+(?:real|main|key)\s+(?:point|problem|issue)\s+is|here(?:['’]s|\s+is)\s+the\s+(?:answer|problem|issue))\b", minimum_word_offset=60, first_match_only=True),), "Detected structure", 10),
)


def variant_matches(variant: Variant, text: str) -> list[re.Match[str]]:
    matches = list(re.compile(variant.regex, re.IGNORECASE).finditer(text or ""))
    if variant.first_match_only:
        matches = matches[:1]
    if variant.minimum_word_offset:
        matches = [
            match
            for match in matches
            if len(re.findall(r"\b\w+(?:['’]\w+)?\b", text[: match.start()]))
            >= variant.minimum_word_offset
        ]
    return matches


def _words(text: str) -> list[str]:
    return re.findall(r"\S+", re.sub(r"[`*_#]+", "", text))


def _context(text: str, start: int, end: int) -> tuple[str, str, str]:
    before_words = _words(text[:start])[-4:]
    after_words = _words(text[end:])[:12]
    before = ("…" if len(_words(text[:start])) > 4 else "") + " ".join(before_words)
    after = " ".join(after_words) + ("…" if len(_words(text[end:])) > 12 else "")
    return before, text[start:end], after


def _instances(pattern: Pattern, replies: list[SessionReply]) -> list[Example]:
    found: list[Example] = []
    seen: set[tuple] = set()
    for reply in replies:
        for variant in pattern.variants:
            for match in variant_matches(variant, reply.text):
                identity = (reply.session_id, match.start(), match.end(), variant.label)
                if identity in seen:
                    continue
                seen.add(identity)
                before, matched, after = _context(reply.text, match.start(), match.end())
                found.append(
                    Example(
                        session_id=reply.session_id,
                        project=reply.project,
                        date=reply.date,
                        before=before,
                        match=matched,
                        after=after,
                    )
                )
    return found


def _representative_examples(instances: list[Example], limit: int = 3) -> tuple[Example, ...]:
    selected: list[Example] = []
    seen_sessions: set[str] = set()
    seen_projects: set[str] = set()
    for require_new_project in (True, False):
        for example in instances:
            if example.session_id in seen_sessions:
                continue
            if require_new_project and example.project in seen_projects:
                continue
            selected.append(example)
            seen_sessions.add(example.session_id)
            seen_projects.add(example.project)
            if len(selected) == limit:
                return tuple(selected)
    return tuple(selected)


def _phrase_pattern(phrase: str, minimum_sessions: int) -> Pattern:
    tokens = phrase.split()
    regex = r"(?<![\w-])" + r"\s+".join(re.escape(token) for token in tokens) + r"(?![\w-])"
    key = "phrase_" + re.sub(r"[^a-z0-9]+", "_", phrase.casefold()).strip("_")[:64]
    return Pattern(
        key=key,
        name=phrase.capitalize(),
        description="Automatically surfaced recurring reply phrase.",
        variants=(Variant(phrase, regex),),
        kind="Discovered phrase",
        minimum_sessions=minimum_sessions,
    )


def _discover_patterns(
    replies: list[SessionReply],
    *,
    minimum_sessions: int,
    limit: int,
) -> tuple[Pattern, ...]:
    occurrences: Counter[str] = Counter()
    sessions: Counter[str] = Counter()
    structural_regexes = [
        re.compile(variant.regex, re.IGNORECASE)
        for pattern in SEED_PATTERNS + STRUCTURAL_PATTERNS
        for variant in pattern.variants
    ]
    for reply in replies:
        found = [phrase for phrase in lexical_phrases(reply.text) if 2 <= len(phrase.split()) <= 3]
        occurrences.update(found)
        sessions.update(set(found))
    ranked: list[tuple[float, str]] = []
    for phrase, session_count in sessions.items():
        if session_count < minimum_sessions:
            continue
        if len(set(phrase.split())) == 1:
            continue
        if any(regex.search(phrase) for regex in structural_regexes):
            continue
        score = session_count * math.log1p(occurrences[phrase] / session_count)
        ranked.append((score, phrase))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    chosen: list[str] = []
    for _score, phrase in ranked:
        if any(phrase in existing or existing in phrase for existing in chosen):
            continue
        chosen.append(phrase)
        if len(chosen) == limit:
            break
    return tuple(_phrase_pattern(phrase, minimum_sessions) for phrase in chosen)


def analyze_habits(
    replies: list[SessionReply],
    *,
    source: str,
    minimum_sessions: int | None = None,
    discovered_limit: int = 15,
) -> HabitReport:
    default_discovery_minimum = max(2, math.ceil(len(replies) * 0.02))
    discovery_minimum = minimum_sessions or default_discovery_minimum
    patterns = SEED_PATTERNS + STRUCTURAL_PATTERNS + _discover_patterns(
        replies,
        minimum_sessions=discovery_minimum,
        limit=max(0, discovered_limit),
    )
    summaries: list[PatternSummary] = []
    for pattern in patterns:
        instances = _instances(pattern, replies)
        session_count = len({example.session_id for example in instances})
        required_sessions = max(3, minimum_sessions or pattern.minimum_sessions)
        if session_count < required_sessions:
            continue
        summaries.append(
            PatternSummary(
                key=pattern.key,
                name=pattern.name,
                description=pattern.description,
                kind=pattern.kind,
                phrases=tuple(variant.label for variant in pattern.variants),
                occurrences=len(instances),
                sessions=session_count,
                projects=len({example.project for example in instances}),
                examples=_representative_examples(instances),
                instances=tuple(instances),
            )
        )
    summaries.sort(key=lambda item: (-item.sessions, -item.occurrences, item.name))
    return HabitReport(
        source=source,
        generated=datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        sessions=len(replies),
        patterns=tuple(summaries),
    )


def session_replies_from_projects(
    projects: list,
    *,
    source: str,
    indexed_replies: dict[str, str] | None = None,
) -> list[SessionReply]:
    replies: list[SessionReply] = []
    for project in projects:
        for conversation in project.conversations:
            if conversation.source != source:
                continue
            text = (indexed_replies or {}).get(str(conversation.path))
            if text is None:
                text = assistant_reply_text(conversation.path)
            if not text:
                continue
            replies.append(
                SessionReply(
                    session_id=conversation.uuid,
                    project=conversation.cwd or project.path,
                    date=(conversation.timestamp or "")[:10],
                    text=text,
                )
            )
    return replies


_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__SOURCE__ language-pattern evidence</title>
<style>
body{font:14px/1.45 ui-sans-serif,system-ui,sans-serif;color:#172033;background:#fff;margin:0}main{max-width:1440px;margin:auto;padding:32px 24px}header{display:flex;justify-content:space-between;gap:24px;border-bottom:1px solid #dbe1ea;padding-bottom:24px;margin-bottom:24px}h1{font-size:24px;margin:0 0 8px}p{margin:0}table{width:100%;border-collapse:collapse;table-layout:fixed}th{font-size:12px;text-transform:uppercase;color:#64748b;text-align:left}th,td{padding:14px 12px;border-bottom:1px solid #dbe1ea;vertical-align:top}.num{text-align:right}.toggle{border:0;background:none;padding:0;color:inherit;font:inherit;text-align:left;cursor:pointer}.name{font-weight:700}.kind,.meta,.status{font-size:12px;color:#64748b}.description{margin-top:5px}.examples p{margin-bottom:8px}.hit{background:#fef3c7;color:#92400e;font-weight:700;padding:1px 4px}.panel{background:#f8fafc;padding:0 24px}.instance{padding:14px 0;border-bottom:1px solid #dbe1ea}.more{display:block;margin:16px auto;background:none;border:0;text-decoration:underline;cursor:pointer}@media(max-width:900px){main{padding:20px 12px}header{display:block}table{min-width:1000px}.wrap{overflow:auto}}
</style></head><body><main><header><div><h1>__SOURCE__ language-pattern evidence</h1><p>Recurring phrases and reproducible writing structures in assistant replies.</p></div><div>__SCOPE__<br>Local report; no conversation text uploaded</div></header><div class="wrap"><table><thead><tr><th>Pattern</th><th>Phrases</th><th>Examples</th><th class="num">Matches</th><th class="num">Conversations</th><th class="num">Projects</th></tr></thead><tbody id="patterns">__ROWS__</tbody></table></div></main>
<script>const DATA=__DATA__;const root=document.querySelector('#patterns'),batch=50;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const excerpt=x=>`${esc(x.before)} <strong class="hit">${esc(x.match)}</strong> ${esc(x.after)}`;function append(state){const next=state.pattern.instances.slice(state.loaded,state.loaded+batch);state.items.insertAdjacentHTML('beforeend',next.map(x=>`<article class="instance"><p>${excerpt(x)}</p><p class="meta">${esc(x.date)} · ${esc(x.project)} · ${esc(x.session_id)}</p></article>`).join(''));state.loaded+=next.length;state.status.textContent=state.loaded===state.pattern.instances.length?`All ${state.loaded} examples shown`:`Showing ${state.loaded} of ${state.pattern.instances.length} examples`;state.more.hidden=state.loaded===state.pattern.instances.length}const states=new Map();function toggle(row){const key=row.dataset.key,panel=root.querySelector(`tr[data-panel="${CSS.escape(key)}"]`),button=row.querySelector('.toggle'),open=button.getAttribute('aria-expanded')==='true';if(!states.has(key)){const pattern=DATA.patterns.find(p=>p.key===key),state={pattern,loaded:0,items:panel.querySelector('.items'),more:panel.querySelector('.more'),status:panel.querySelector('.status')};state.more.addEventListener('click',event=>{event.stopPropagation();append(state)});states.set(key,state);append(state)}button.setAttribute('aria-expanded',String(!open));button.querySelector('[aria-hidden]').textContent=open?'▸':'▾';panel.hidden=open}root.querySelectorAll('tr[data-key]').forEach(row=>row.addEventListener('click',()=>toggle(row)));</script></body></html>"""


def _example_html(example: Example, *, overview: bool = False) -> str:
    marker = ' data-overview-example="true"' if overview else ""
    return (
        f"<p{marker}>{html.escape(example.before)} "
        f'<strong class="hit">{html.escape(example.match)}</strong> '
        f"{html.escape(example.after)}</p>"
    )


def _overview_rows(report: HabitReport) -> str:
    rows: list[str] = []
    for pattern in report.patterns:
        key = html.escape(pattern.key, quote=True)
        examples = "".join(_example_html(example, overview=True) for example in pattern.examples)
        rows.append(
            f'<tr data-key="{key}"><td><button class="toggle" aria-expanded="false">'
            '<span aria-hidden="true">▸</span> '
            f'<span class="name">{html.escape(pattern.name)}</span></button>'
            f'<div class="kind">{html.escape(pattern.kind)}</div>'
            f'<div class="description">{html.escape(pattern.description)}</div></td>'
            f"<td>{' · '.join(html.escape(phrase) for phrase in pattern.phrases)}</td>"
            f'<td class="examples">{examples}</td>'
            f'<td class="num">{pattern.occurrences}</td>'
            f'<td class="num">{pattern.sessions}</td>'
            f'<td class="num">{pattern.projects}</td></tr>'
            f'<tr hidden data-panel="{key}"><td colspan="6" class="panel">'
            '<div class="items"></div><button class="more" type="button">'
            'Show 50 more</button><p class="status" aria-live="polite"></p></td></tr>'
        )
    return "".join(rows)


def render_html(report: HabitReport) -> str:
    payload = json.dumps(report.public_dict(), ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    public = report.public_dict()
    scope = (
        f"{public['pattern_count']} patterns · {public['match_count']:,} matches · "
        f"{report.sessions} conversations searched"
    )
    return (
        _HTML_TEMPLATE.replace("__DATA__", payload)
        .replace("__ROWS__", _overview_rows(report))
        .replace("__SOURCE__", html.escape(report.source.title()))
        .replace("__SCOPE__", html.escape(scope))
    )


def write_report(report: HabitReport, output: Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(report), encoding="utf-8")
    output.with_suffix(".json").write_text(
        json.dumps(report.public_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output

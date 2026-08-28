"""L1 rule 2 in code: a quote is only admissible if it's in explicit quotation
marks. Regex finds each quote span, then resolves who said it; speaker
resolution against `persons` and concept filtering happen after, so a
candidate only survives if BOTH the speaker and the concept are ones we
actually track.

Candidates always land in review_queue/candidates.json with `approved: false`.
Nothing here writes to `claims`/`events` -- pipeline/review/apply_approved.py
is the only thing that does, and only for entries a human flipped to `true`.
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "classify"))
from grammatical_form import claim_level_form, find_occurrences  # noqa: E402

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
CONTEXT_WINDOW_CHARS = 120
# How far around a quote to look for its attribution (verb/name/pronoun).
ATTRIBUTION_WINDOW_CHARS = 60

# Hebrew quotation marks in the wild: straight ", curly “ ”, gershayim ״
QUOTE_CHARS = r"[\"“”״]"
QUOTE_SPAN = re.compile(QUOTE_CHARS + r"([^\"“”״]{10,400})" + QUOTE_CHARS)

# Both past tense (classic reported speech: "אמר X") and present/benoni tense
# (common in Hebrew news narration: X מסביר, "..."). The present-tense forms
# were missing entirely -- found on a real article (Lieberman, Maariv
# 2021-03-20) that used ONLY "מסביר" and matched nothing at all, not a
# hypothetical gap.
SPEECH_VERBS = r"(?:" + "|".join([
    "אמר", "אמרה", "אומר", "אומרת",
    "הצהיר", "הצהירה", "מצהיר", "מצהירה",
    "טען", "טענה", "טוען", "טוענת",
    "כתב", "כתבה", "כותב", "כותבת",
    "ציין", "ציינה", "מציין", "מציינת",
    "הוסיף", "הוסיפה", "מוסיף", "מוסיפה",
    "מסר", "מסרה", "מוסר", "מוסרת",
    "הסביר", "הסבירה", "מסביר", "מסבירה",
    "הבהיר", "הבהירה", "מבהיר", "מבהירה",
    "השיב", "השיבה", "משיב", "משיבה",
]) + r")"

# A journalist who already named the speaker once often refers back with a
# bare pronoun for later quotes in the same piece ("הוא מסביר", not repeating
# the name) -- same real article, not hypothetical.
PRONOUN_SPEAKERS = r"(?:הוא|היא)"

NAME_AFTER_VERB = r"([א-ת\"'\s]{2,30}?)(?=[,.:\n]|$)"
NAME_BEFORE_QUOTE = r"([א-ת]{2,15}\s[א-ת']{2,20})"

# quote, then attribution: "..." אמר X   /   "..." — כך אמר X

# Optional discourse connector between the dash and the verb -- "..." — כך
# אמר X. Pre-existing gap: [\s,—-]* alone never covered כ/ך (not whitespace
# or dash), so this documented pattern (module docstring, "quote, then
# attribution") never actually matched anything even before this file's
# broader rewrite -- caught by testing the documented example directly, not
# a hypothetical.
DISCOURSE_CONNECTOR = r"(?:כך\s+)?"

ATTR_AFTER_NAME = re.compile(r"^[\s,—-]*" + DISCOURSE_CONNECTOR + SPEECH_VERBS + r"\s+" + NAME_AFTER_VERB)
ATTR_AFTER_PRONOUN = re.compile(r"^[\s,—-]*" + DISCOURSE_CONNECTOR + PRONOUN_SPEAKERS + r"\s+" + SPEECH_VERBS)
# attribution, then quote: X: "..."   /   X אמר: "..."
ATTR_BEFORE_NAME = re.compile(NAME_BEFORE_QUOTE + r"[,:]?\s*(?:" + SPEECH_VERBS + r")?\s*:?\s*$")
ATTR_BEFORE_PRONOUN = re.compile(PRONOUN_SPEAKERS + r"[,:]?\s*(?:" + SPEECH_VERBS + r")?\s*:?\s*$")


@dataclass
class Candidate:
    text_he: str
    context_before: str
    context_after: str
    attributed_name: str
    person_id: int | None
    concept: str
    concept_grammatical_form: str | None
    claim_date: str | None
    source_platform: str
    article_url: str
    article_title: str
    approved: bool = field(default=False)


def load_persons(conn: sqlite3.Connection) -> dict[str, int]:
    """'first last' -> person_id. Deliberately NOT filtered to is_current=1: that
    flag means "sitting MK right now", which excludes party leaders/candidates
    who aren't currently seated (e.g. Golan, campaigning but not a sitting MK) --
    exactly the people this project needs to track. False-match risk from the
    wider pool is accepted here; human review is the actual safeguard."""
    rows = conn.execute("SELECT person_id, first_name, last_name FROM persons").fetchall()
    return {f"{first} {last}": pid for pid, first, last in rows}


def resolve_speaker(name_guess: str, name_to_id: dict[str, int]) -> tuple[str, int] | None:
    name_guess = name_guess.strip()
    for full_name, pid in name_to_id.items():
        if full_name == name_guess or full_name in name_guess or name_guess in full_name:
            return full_name, pid
    return None


def matching_concepts(text: str, concepts: list[str]) -> list[str]:
    """Delegates to find_occurrences (not a separate \\b-based regex) so a
    concept is only ever flagged as a candidate if find_occurrences can ALSO
    locate and attempt to classify the same span. \\b alone matched a hyphen
    as a word boundary, so "אנטי-ציוניים" created a candidate tagged concept
    "ציוני" with concept_grammatical_form always None -- find_occurrences
    correctly declines a hyphen (not whitespace) as a real boundary, since
    compound anti-X forms are deliberately not auto-extracted yet (spec.md
    L2.1, anti_class). Found from a real candidate, not a hypothetical."""
    return [concept for concept in concepts if find_occurrences(text, concept)]


def surrounding_context(article_text: str, span: tuple[int, int]) -> tuple[str, str]:
    """L1 rule 3: context_before/after are mandatory, not optional. Window-based
    (not sentence-parsed) -- mechanical and honest about being a rough cut, not
    linguistically precise."""
    start, end = span
    before = article_text[max(0, start - CONTEXT_WINDOW_CHARS):start].strip()
    after = article_text[end:end + CONTEXT_WINDOW_CHARS].strip()
    return before, after


def _resolve_touching_attribution(
    article_text: str, span: tuple[int, int], name_to_id: dict[str, int]
) -> tuple[str, int] | None | str:
    """Attribution that directly touches this quote (name or pronoun, before
    or after). Returns a resolved (name, person_id), the sentinel "pronoun"
    (caller substitutes the last resolved speaker), the sentinel "unresolved"
    (a NAME was found but isn't one of our tracked persons -- a real,
    different speaker we just don't track, so the caller must NOT fall back
    to the previous speaker), or None (no attribution touches this quote at
    all, so the caller may consider carry-forward)."""
    start, end = span
    after = article_text[end:end + ATTRIBUTION_WINDOW_CHARS]
    before = article_text[max(0, start - ATTRIBUTION_WINDOW_CHARS):start]

    m = ATTR_AFTER_NAME.match(after)
    if m:
        return resolve_speaker(m.group(1), name_to_id) or "unresolved"

    m = ATTR_BEFORE_NAME.search(before)
    if m:
        return resolve_speaker(m.group(1), name_to_id) or "unresolved"

    if ATTR_AFTER_PRONOUN.match(after) or ATTR_BEFORE_PRONOUN.search(before):
        return "pronoun"

    return None


def extract_candidates(article_text: str, article_url: str, article_title: str,
                        claim_date: str | None, source_platform: str,
                        name_to_id: dict[str, int], concepts: list[str]) -> list[Candidate]:
    candidates = []
    last_speaker: tuple[str, int] | None = None
    last_quote_end: int | None = None

    for match in QUOTE_SPAN.finditer(article_text):
        quote = match.group(1).strip()
        start, end = match.span()

        attribution = _resolve_touching_attribution(article_text, (start, end), name_to_id)

        if attribution == "unresolved":
            # A real, named attribution we just don't track -- breaks the
            # carry-forward chain so a LATER pronoun-only quote doesn't get
            # wrongly attributed to whoever spoke before this interruption.
            last_speaker = None
            last_quote_end = None
            continue

        if attribution == "pronoun":
            speaker = last_speaker
        elif attribution is not None:
            speaker = attribution
        elif (last_speaker is not None and last_quote_end is not None
              and article_text[last_quote_end:start].strip("\n\t .,—-") == ""):
            # No attribution at all touches this quote, but it directly
            # follows the last (attributed) one with nothing but
            # whitespace/punctuation between -- consecutive quotes from one
            # speaker, attributed once (real pattern: Lieberman, Maariv
            # 2021-03-20, second quote has zero attribution of its own).
            speaker = last_speaker
        else:
            speaker = None

        if speaker is None:
            continue
        full_name, person_id = speaker
        last_speaker, last_quote_end = speaker, end

        hit_concepts = matching_concepts(quote, concepts)
        if not hit_concepts:
            continue

        before, after = surrounding_context(article_text, (start, end))

        for concept in hit_concepts:
            form = claim_level_form(find_occurrences(quote, concept))
            candidates.append(Candidate(
                text_he=quote, context_before=before, context_after=after,
                attributed_name=full_name, person_id=person_id, concept=concept,
                concept_grammatical_form=form, claim_date=claim_date,
                source_platform=source_platform, article_url=article_url,
                article_title=article_title,
            ))
    return candidates


QUEUE_PATH = Path(__file__).resolve().parents[1] / "review_queue" / "candidates.json"


def merge_into_queue(new_candidates: list[dict], queue_path: Path = QUEUE_PATH) -> int:
    """Merges new candidates into the existing queue file instead of overwriting
    it -- multiple sources (news_rss, telegram_scrape) now feed the same queue,
    and a human may have partially reviewed what's already there. Dedupes on
    (platform, url, concept, text) so re-running a source on a schedule doesn't
    pile up the same candidate over and over."""
    existing = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else []
    seen = {(c.get("source_platform"), c.get("article_url"), c.get("concept"), c.get("text_he"))
            for c in existing}
    added = 0
    for c in new_candidates:
        key = (c.get("source_platform"), c.get("article_url"), c.get("concept"), c.get("text_he"))
        if key not in seen:
            existing.append(c)
            seen.add(key)
            added += 1
    queue_path.parent.mkdir(exist_ok=True)
    queue_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


if __name__ == "__main__":
    from dataclasses import asdict

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from concepts import CONCEPTS  # noqa: E402
    from news_rss import fetch_all_articles, fetch_article_text

    conn = sqlite3.connect(DB_PATH)
    name_to_id = load_persons(conn)
    concepts = CONCEPTS
    conn.close()

    all_candidates: list[Candidate] = []
    for article in fetch_all_articles(per_feed_limit=15):
        try:
            text = fetch_article_text(article.url)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {article.url}: {exc}")
            continue
        all_candidates.extend(
            extract_candidates(text, article.url, article.title, article.pub_date,
                                article.platform, name_to_id, concepts)
        )

    added = merge_into_queue([asdict(c) for c in all_candidates])
    print(f"{len(all_candidates)} candidates found, {added} new -> {QUEUE_PATH}")

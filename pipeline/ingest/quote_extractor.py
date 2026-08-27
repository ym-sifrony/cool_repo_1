"""L1 rule 2 in code: a quote is only admissible if it's in explicit quotation
marks. Regex finds quote+attribution pairs; speaker resolution against `persons`
and concept filtering happen after, so a candidate only survives if BOTH the
speaker and the concept are ones we actually track.

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

# Hebrew quotation marks in the wild: straight ", curly “ ”, gershayim ״
QUOTE_CHARS = r"[\"“”״]"
SPEECH_VERBS = r"(?:אמר|אמרה|הצהיר|הצהירה|טען|טענה|כתב|כתבה|ציין|ציינה|הוסיף|הוסיפה|מסר|מסרה)"

# quote, then attribution: "..." אמר X   /   "..." — כך אמר X
QUOTE_THEN_ATTR = re.compile(
    QUOTE_CHARS + r"([^\"“”״]{10,400})" + QUOTE_CHARS
    + r"[\s,—-]*" + SPEECH_VERBS + r"\s+([א-ת\"'\s]{2,30}?)(?=[,.:\n]|$)"
)
# attribution, then quote: X: "..."   /   X אמר: "..."
ATTR_THEN_QUOTE = re.compile(
    r"([א-ת]{2,15}\s[א-ת']{2,20})[,:]?\s*(?:" + SPEECH_VERBS + r")?\s*:?\s*"
    + QUOTE_CHARS + r"([^\"“”״]{10,400})" + QUOTE_CHARS
)


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


def extract_candidates(article_text: str, article_url: str, article_title: str,
                        claim_date: str | None, source_platform: str,
                        name_to_id: dict[str, int], concepts: list[str]) -> list[Candidate]:
    candidates = []
    for pattern in (QUOTE_THEN_ATTR, ATTR_THEN_QUOTE):
        for match in pattern.finditer(article_text):
            groups = match.groups()
            quote, name_guess = (groups[0], groups[1]) if pattern is QUOTE_THEN_ATTR else (groups[1], groups[0])
            quote = quote.strip()

            resolved = resolve_speaker(name_guess, name_to_id)
            if not resolved:
                continue
            full_name, person_id = resolved

            hit_concepts = matching_concepts(quote, concepts)
            if not hit_concepts:
                continue

            before, after = surrounding_context(article_text, match.span())

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

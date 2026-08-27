"""L1 rule 2 in code: a quote is only admissible if it's in explicit quotation
marks. Regex finds quote+attribution pairs; speaker resolution against `persons`
and concept filtering happen after, so a candidate only survives if BOTH the
speaker and the concept are ones we actually track. Output is always a review
candidate -- nothing here writes to `claims` directly.
"""
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "classify"))
from grammatical_form import inflected_forms  # noqa: E402

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"

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
    attributed_name: str
    person_id: int | None
    concept: str
    article_url: str


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
    hits = []
    for concept in concepts:
        forms = inflected_forms(concept)
        if any(re.search(r"\b" + re.escape(f) + r"\b", text) for f in forms):
            hits.append(concept)
    return hits


def extract_candidates(article_text: str, article_url: str,
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

            for concept in matching_concepts(quote, concepts):
                candidates.append(Candidate(quote, full_name, person_id, concept, article_url))
    return candidates


if __name__ == "__main__":
    import json

    from news_rss import fetch_all_articles, fetch_article_text

    conn = sqlite3.connect(DB_PATH)
    name_to_id = load_persons(conn)
    concepts = [r[0] for r in conn.execute("SELECT DISTINCT concept FROM claims")]
    conn.close()

    all_candidates = []
    for article in fetch_all_articles()[:15]:
        try:
            text = fetch_article_text(article.url)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {article.url}: {exc}")
            continue
        for c in extract_candidates(text, article.url, name_to_id, concepts):
            all_candidates.append(vars(c) | {"article_title": article.title})

    out_path = Path(__file__).resolve().parents[1] / "review_queue" / "candidates.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(all_candidates)} candidates -> {out_path}")

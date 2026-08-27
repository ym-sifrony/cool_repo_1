"""L0 for Telegram (spec.md L1 rule 2.ב): scrapes the public preview page
(t.me/s/<channel>) -- no API key, no login, no bot, same cost/security
profile as any other GET request in this pipeline.

Channel-to-person mapping comes ONLY from telegram_channel_registry
(pipeline/db/schema.sql), which a human populates and verifies manually --
this script never guesses or infers ownership.

A channel post is first-person speech with no journalist paraphrasing it, so
the quotation-mark test from quote_extractor.py doesn't apply -- but that is
NOT a shortcut past human review. Every candidate still lands in the queue
with approved: false like any other source. The one thing this script DOES
filter automatically: forwarded posts ("Forwarded from" -- detected via the
real .tgme_widget_message_forwarded_from marker Telegram's own widget HTML
uses) are someone else's words, not the channel owner's, so they're dropped
before ever becoming a candidate.
"""
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_extractor import Candidate, matching_concepts, merge_into_queue  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "classify"))
from grammatical_form import claim_level_form, find_occurrences  # noqa: E402

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
HEADERS = {
    "User-Agent": "ConceptMapBot/0.1 (civic research project; contact: y.m.sifrony100@gmail.com)"
}
REQUEST_DELAY_SECONDS = 1.0
CONTEXT_WINDOW_CHARS = 120


@dataclass
class TelegramPost:
    text: str
    post_url: str
    pub_date: str | None
    is_forward: bool


def fetch_channel_posts(username: str) -> list[TelegramPost]:
    url = f"https://t.me/s/{username}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    for msg in soup.select(".tgme_widget_message"):
        text_el = msg.select_one(".tgme_widget_message_text")
        if text_el is None:
            continue  # media-only post (photo/video, no caption) -- nothing to extract
        date_el = msg.select_one(".tgme_widget_message_date time")
        data_post = msg.get("data-post")  # "<username>/<message_id>"
        posts.append(TelegramPost(
            text=text_el.get_text(separator="\n", strip=True),
            post_url=f"https://t.me/{data_post}" if data_post else url,
            pub_date=date_el.get("datetime") if date_el else None,
            is_forward=msg.select_one(".tgme_widget_message_forwarded_from") is not None,
        ))
    return posts


def load_registry(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT person_id, channel_username FROM telegram_channel_registry WHERE is_active = 1"
    ).fetchall()
    return list(rows)


def extract_candidates_from_channel(person_id: int, username: str,
                                     posts: list[TelegramPost],
                                     concepts: list[str]) -> list[Candidate]:
    """context_before/after here are the neighboring posts, not a text window
    within one document -- posts are already self-contained units, so 'context'
    is what surrounded the post in the channel's timeline."""
    candidates = []
    originals = [p for p in posts if not p.is_forward]

    for i, post in enumerate(originals):
        hit_concepts = matching_concepts(post.text, concepts)
        if not hit_concepts:
            continue

        before = originals[i - 1].text[-CONTEXT_WINDOW_CHARS:] if i > 0 else ""
        after = originals[i + 1].text[:CONTEXT_WINDOW_CHARS] if i + 1 < len(originals) else ""
        claim_date = post.pub_date.split("T")[0] if post.pub_date else None

        for concept in hit_concepts:
            form = claim_level_form(find_occurrences(post.text, concept))
            candidates.append(Candidate(
                text_he=post.text, context_before=before, context_after=after,
                attributed_name=f"telegram:@{username}", person_id=person_id,
                concept=concept, concept_grammatical_form=form,
                claim_date=claim_date, source_platform="telegram",
                article_url=post.post_url, article_title=f"@{username}",
            ))
    return candidates


if __name__ == "__main__":
    from dataclasses import asdict

    conn = sqlite3.connect(DB_PATH)
    registry = load_registry(conn)
    concepts = [r[0] for r in conn.execute("SELECT DISTINCT concept FROM claims")]
    conn.close()

    if not registry:
        print("telegram_channel_registry is empty -- nothing to scrape.\n"
              "Add a manually-verified row first, e.g.:\n"
              "  INSERT INTO telegram_channel_registry VALUES\n"
              "  (<person_id>, '<channel_username>', '<how you confirmed ownership>',\n"
              "   '<url where you found the link>', '<your name>', '<iso date>', 1);")
        sys.exit(0)

    all_candidates: list[Candidate] = []
    for person_id, username in registry:
        try:
            posts = fetch_channel_posts(username)
        except Exception as exc:  # noqa: BLE001
            print(f"skip @{username}: {exc}")
            continue
        all_candidates.extend(
            extract_candidates_from_channel(person_id, username, posts, concepts)
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    added = merge_into_queue([asdict(c) for c in all_candidates])
    print(f"{len(all_candidates)} candidates found, {added} new -> review_queue/candidates.json")

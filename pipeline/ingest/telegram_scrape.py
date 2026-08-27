"""L0 for Telegram (spec.md L1 rule 2.ב): scrapes the public preview page
(t.me/s/<channel>) -- no API key, no login, no bot, same cost/security
profile as any other GET request in this pipeline.

THREE structurally different kinds of channel, not one:

1. OFFICIAL channel of a speaker (from telegram_channel_registry) -- the
   owner IS the speaker, first-person, no journalist paraphrasing it, so the
   quotation-mark test doesn't apply and the whole post is admissible as-is.
   Channel-to-person mapping comes ONLY from the manually-verified registry
   table -- never guessed. Forwarded posts ARE excluded here (detected via
   Telegram's own .tgme_widget_message_forwarded_from marker): they're
   someone else's words, not the channel owner's.

2. REPORT channel (REPORT_CHANNELS below) -- a journalist/commentary
   channel that reports on OTHER people's statements using ordinary
   name+quote attribution ("X said: '...'"), structurally identical to a
   news article: runs through the same quote+attribution+resolve_speaker
   pipeline as quote_extractor.py. No ownership registry needed -- we're
   not claiming the channel owner said anything.

3. HUMAN-REVIEW channel (HUMAN_REVIEW_CHANNELS below) -- a small,
   idiosyncratic source where mechanical extraction keeps missing real
   content (e.g. attribution to a ROLE like "הרמטכ״ל" rather than a name --
   resolve_speaker only matches names, and role-to-current-holder
   resolution is a real, time-sensitive feature we haven't built). No
   extraction is attempted at all: every new post is queued verbatim into
   review_queue/reading_list.json with read: false for a human to read
   directly and, if something's worth keeping, add by hand via
   manual_entry.py. This is NOT the same gate as candidates.json's
   approved: false -- nothing here is a pre-filled extraction to approve or
   reject, it's raw material nobody has looked at yet.

None of the three modes is a shortcut past human judgment -- modes 1 and 2
still land in candidates.json with approved: false like any other source;
mode 3 skips straight to a human because mechanical extraction has already
been shown not to fit that source.
"""
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quote_extractor import (  # noqa: E402
    Candidate, extract_candidates, load_persons, matching_concepts, merge_into_queue,
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "classify"))
from grammatical_form import claim_level_form, find_occurrences  # noqa: E402

# Journalist/commentary channels to mine for name+quote attribution (mode 2).
REPORT_CHANNELS: list[str] = []

# Small/idiosyncratic channels a human reads directly (mode 3) -- see module
# docstring for why this is a different track than REPORT_CHANNELS.
# (Identity check, not ownership: t.me/s/amitsegal's own self-declared title
# reads "עמית סגל", confirmed 2026-08-27.)
HUMAN_REVIEW_CHANNELS = [
    "amitsegal",
]

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
READING_LIST_PATH = Path(__file__).resolve().parents[1] / "review_queue" / "reading_list.json"
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


def extract_candidates_from_report_channel(username: str, posts: list[TelegramPost],
                                            name_to_id: dict[str, int],
                                            concepts: list[str]) -> list[Candidate]:
    """Each post is scanned like a news article -- quote+attribution regex,
    resolve_speaker against the real persons table, concept match. The
    channel owner is never assumed to be the speaker."""
    candidates = []
    for post in posts:
        claim_date = post.pub_date.split("T")[0] if post.pub_date else None
        candidates.extend(
            extract_candidates(post.text, post.post_url, f"@{username}",
                                claim_date, "telegram", name_to_id, concepts)
        )
    return candidates


def queue_for_human_review(username: str, posts: list[TelegramPost]) -> int:
    """No extraction attempted -- every non-forward post becomes a raw reading-
    list entry (read: false), deduped by post_url across runs so a human only
    ever sees a post once. Separate file from candidates.json on purpose: that
    file's approved:false means 'a pre-filled extraction awaiting a decision',
    this one's read:false means 'nobody has looked at this yet at all'."""
    entries = (json.loads(READING_LIST_PATH.read_text(encoding="utf-8"))
               if READING_LIST_PATH.exists() else [])
    seen = {e["post_url"] for e in entries}
    added = 0
    for post in posts:
        if post.is_forward or post.post_url in seen:
            continue
        entries.append({
            "channel": username, "text": post.text, "post_url": post.post_url,
            "pub_date": post.pub_date, "read": False,
        })
        seen.add(post.post_url)
        added += 1
    READING_LIST_PATH.parent.mkdir(exist_ok=True)
    READING_LIST_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


if __name__ == "__main__":
    from dataclasses import asdict

    conn = sqlite3.connect(DB_PATH)
    registry = load_registry(conn)
    name_to_id = load_persons(conn)
    concepts = [r[0] for r in conn.execute("SELECT DISTINCT concept FROM claims")]
    conn.close()

    all_candidates: list[Candidate] = []

    if not registry:
        print("telegram_channel_registry is empty -- no official channels to scrape.\n"
              "Add a manually-verified row first, e.g.:\n"
              "  INSERT INTO telegram_channel_registry VALUES\n"
              "  (<person_id>, '<channel_username>', '<how you confirmed ownership>',\n"
              "   '<url where you found the link>', '<your name>', '<iso date>', 1);")
    for person_id, username in registry:
        try:
            posts = fetch_channel_posts(username)
        except Exception as exc:  # noqa: BLE001
            print(f"skip official channel @{username}: {exc}")
            continue
        all_candidates.extend(
            extract_candidates_from_channel(person_id, username, posts, concepts)
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    for username in REPORT_CHANNELS:
        try:
            posts = fetch_channel_posts(username)
        except Exception as exc:  # noqa: BLE001
            print(f"skip report channel @{username}: {exc}")
            continue
        all_candidates.extend(
            extract_candidates_from_report_channel(username, posts, name_to_id, concepts)
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    added = merge_into_queue([asdict(c) for c in all_candidates])
    print(f"{len(all_candidates)} candidates found, {added} new -> review_queue/candidates.json")

    reading_added = 0
    for username in HUMAN_REVIEW_CHANNELS:
        try:
            posts = fetch_channel_posts(username)
        except Exception as exc:  # noqa: BLE001
            print(f"skip human-review channel @{username}: {exc}")
            continue
        reading_added += queue_for_human_review(username, posts)
        time.sleep(REQUEST_DELAY_SECONDS)
    print(f"{reading_added} new posts -> review_queue/reading_list.json")

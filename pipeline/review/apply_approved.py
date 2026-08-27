"""Reads review_queue/candidates.json and inserts every entry with
`approved: true` into `claims` -- nothing else touches that table for
regex-extracted candidates. This script running IS the human-review gate
required for extraction.method: regex (spec.md L1 rule 2 + the security
section's review-gate rule): a human edits candidates.json, flips
`approved: true` only after checking the quote against the real article,
then runs this.

Deliberately does NOT create `events`. Event decomposition (deciding gt vs
eq_ordinal vs in_class/not_in_class/anti_class between two specific named
entities) from arbitrary extracted text is a harder, separate judgment call --
same rigor we've applied everywhere else in L1/L2.1, not something to
auto-generate alongside claim insertion. anti_class in particular needs a
human call on whether THIS speaker treats "anti-X" as its own class rather
than a rephrasing of "not X" (spec.md L2.1) -- never inferred mechanically.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
QUEUE_PATH = Path(__file__).resolve().parents[1] / "review_queue" / "candidates.json"


def checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_claim_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT id FROM claims ORDER BY id DESC LIMIT 1").fetchone()
    n = int(row[0].split("_")[1]) + 1 if row else 1
    return f"clm_{n:05d}"


def main() -> None:
    if not QUEUE_PATH.exists():
        print(f"no queue file at {QUEUE_PATH}")
        return

    candidates = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    approved = [c for c in candidates if c.get("approved")]
    if not approved:
        print("nothing marked approved: true -- edit candidates.json first")
        return

    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    for c in approved:
        if not c.get("claim_date"):
            print(f"skip (no date, can't satisfy L1 schema): {c['text_he'][:40]}...")
            continue

        claim_id = next_claim_id(conn)
        conn.execute(
            """INSERT INTO claims
               (id, person_id, concept, text_he, context_before, context_after,
                claim_date, source_medium, source_platform, source_url, source_locator,
                source_retrieved_at, source_checksum, source_status,
                extraction_method, extraction_confidence, reviewed_by,
                concept_grammatical_form)
               VALUES (:id, :person_id, :concept, :text_he, :context_before, :context_after,
                       :claim_date, 'text', :source_platform, :article_url, NULL,
                       :retrieved_at, :checksum, 'live',
                       'regex', 0.7, :reviewed_by, :form)""",
            {
                "id": claim_id, "person_id": c["person_id"], "concept": c["concept"],
                "text_he": c["text_he"], "context_before": c["context_before"],
                "context_after": c["context_after"], "claim_date": c["claim_date"],
                "source_platform": c["source_platform"], "article_url": c["article_url"],
                "retrieved_at": now_iso(), "checksum": checksum(c["text_he"]),
                "reviewed_by": "manual-approval-queue",
                "form": c.get("concept_grammatical_form"),
            },
        )
        inserted += 1
        print(f"{claim_id}: {c['text_he'][:50]}...")

    conn.commit()
    conn.close()
    print(f"inserted {inserted} claims (no events -- add those separately, deliberately)")


if __name__ == "__main__":
    main()

"""Export claims/events/classification snapshots to JSON for the Astro site to
read at build time. The site never queries SQLite directly -- this is the one
bridge between the DB (never committed, .gitignore'd) and the static files
that ship in the build.

Repo layout decided later than this comment originally said: one repo
(pipeline/ + site/ together), kept Private on GitHub -- not the earlier
two-repo private-pipeline/public-site split. The deployed SITE is still
fully public (via Vercel/Cloudflare Pages reading the private repo with
read-only access); it's the source repo that stays closed. See spec.md's
security section.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "classify"))
from l2_1 import classify_all  # noqa: E402

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
OUT_DIR = Path(__file__).resolve().parents[2] / "site" / "src" / "data"


def entity_label(conn: sqlite3.Connection, entity_id: str | None) -> str | None:
    """'person:30713' / 'faction:1096' -> display name, resolved from the DB."""
    if entity_id is None:
        return None
    kind, raw_id = entity_id.split(":")
    if kind == "person":
        row = conn.execute(
            "SELECT first_name, last_name FROM persons WHERE person_id = ?", (raw_id,)
        ).fetchone()
        return f"{row[0]} {row[1]}" if row else entity_id
    if kind == "faction":
        row = conn.execute(
            "SELECT name FROM factions WHERE faction_id = ?", (raw_id,)
        ).fetchone()
        return row[0].strip() if row else entity_id
    return entity_id


def export_concept(conn: sqlite3.Connection, concept: str) -> dict:
    # visible=1 filter: a claim can be accurate (approved into `claims`) and
    # still deliberately unpublished by a curator -- `visible` is a separate
    # editorial gate, not a duplicate of the extraction-accuracy approval.
    claim_rows = conn.execute(
        """SELECT c.id, p.first_name, p.last_name, c.text_he, c.context_before,
                  c.context_after, c.claim_date, c.concept_grammatical_form,
                  c.source_medium, c.source_platform, c.source_url, c.source_status
           FROM claims c JOIN persons p ON p.person_id = c.person_id
           WHERE c.concept = ? AND c.visible = 1
           ORDER BY c.claim_date""",
        (concept,),
    ).fetchall()

    claims = [
        {
            "id": r[0], "speaker": f"{r[1]} {r[2]}", "text_he": r[3],
            "context_before": r[4], "context_after": r[5], "date": r[6],
            "grammatical_form": r[7], "source_medium": r[8],
            "source_platform": r[9], "source_url": r[10], "source_status": r[11],
        }
        for r in claim_rows
    ]

    events_rows = conn.execute(
        """SELECT e.id, e.claim_id, e.relation, e.subject_id, e.object_id
           FROM events e JOIN claims c ON c.id = e.claim_id
           WHERE e.concept = ? AND c.visible = 1""",
        (concept,),
    ).fetchall()
    events = [
        {"id": r[0], "claim_id": r[1], "relation": r[2],
         "subject": entity_label(conn, r[3]), "object": entity_label(conn, r[4])}
        for r in events_rows
    ]

    # visible_only=True: a classification must never rest on a claim the
    # reader can't see -- same reasoning as the claims/events filters above.
    classifications = [
        {
            "speaker": entity_label(conn, f"person:{c['person_id']}"),
            "form": c["form"], "classification": c["classification"],
            "universe": [entity_label(conn, u) for u in c["universe"]],
            "violation_count": len(c["violations"]),
        }
        for c in classify_all(conn, visible_only=True) if c["concept"] == concept
    ]

    return {"concept": concept, "claims": claims, "events": events,
            "classifications": classifications}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    concepts = [r[0] for r in conn.execute("SELECT DISTINCT concept FROM claims")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for concept in concepts:
        data = export_concept(conn, concept)
        out_path = OUT_DIR / f"{concept}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"concept": concept, "claim_count": len(data["claims"])})
        print(f"{concept}: {len(data['claims'])} claims -> {out_path}")

    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    conn.close()


if __name__ == "__main__":
    main()

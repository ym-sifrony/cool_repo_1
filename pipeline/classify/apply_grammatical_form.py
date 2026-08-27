"""Writes concept_grammatical_form to claims, using grammatical_form.py.
Regex output -- manually reviewed against all 5 real claims in this session
before being applied, so reviewed_by is set rather than left null.
"""
import sqlite3
from pathlib import Path

from grammatical_form import claim_level_form, find_occurrences

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, concept, text_he FROM claims").fetchall()

    for claim_id, concept, text in rows:
        form = claim_level_form(find_occurrences(text, concept))
        conn.execute(
            """UPDATE claims SET concept_grammatical_form = ?,
               reviewed_by = COALESCE(reviewed_by, ?) WHERE id = ?""",
            (form, "manual-review-2026-08-26", claim_id),
        )
        print(f"{claim_id} ({concept}): {form}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()

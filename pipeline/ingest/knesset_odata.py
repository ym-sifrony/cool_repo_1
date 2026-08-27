"""Fetch reference data (persons, factions) from the official Knesset OData service
into the local SQLite database. Read-only against an official API, but still rate-limited
and identified per the scraping-etiquette policy in spec.md section on security.
"""
import argparse
import sqlite3
import time
from pathlib import Path

import requests

BASE = "https://knesset.gov.il/Odata/ParliamentInfo.svc"
HEADERS = {
    "User-Agent": "ConceptMapBot/0.1 (civic research project; contact: y.m.sifrony100@gmail.com)"
}
PAGE_SIZE = 100
REQUEST_DELAY_SECONDS = 0.5

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def fetch_all(collection: str, select: str) -> list[dict]:
    records = []
    skip = 0
    while True:
        params = {
            "$select": select,
            "$top": PAGE_SIZE,
            "$skip": skip,
            "$format": "json",
        }
        resp = requests.get(f"{BASE}/{collection}", params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        page = resp.json()["value"]
        if not page:
            break
        records.extend(page)
        skip += PAGE_SIZE
        time.sleep(REQUEST_DELAY_SECONDS)
    return records


def load_persons(conn: sqlite3.Connection) -> int:
    rows = fetch_all("KNS_Person", "PersonID,FirstName,LastName,IsCurrent,LastUpdatedDate")
    conn.executemany(
        """INSERT INTO persons (person_id, first_name, last_name, is_current, last_updated)
           VALUES (:PersonID, :FirstName, :LastName, :IsCurrent, :LastUpdatedDate)
           ON CONFLICT(person_id) DO UPDATE SET
             first_name=excluded.first_name, last_name=excluded.last_name,
             is_current=excluded.is_current, last_updated=excluded.last_updated""",
        rows,
    )
    conn.commit()
    return len(rows)


def load_factions(conn: sqlite3.Connection) -> int:
    rows = fetch_all(
        "KNS_Faction", "FactionID,Name,IsCurrent,KnessetNum,StartDate,FinishDate"
    )
    conn.executemany(
        """INSERT INTO factions (faction_id, name, is_current, knesset_num, start_date, finish_date)
           VALUES (:FactionID, :Name, :IsCurrent, :KnessetNum, :StartDate, :FinishDate)
           ON CONFLICT(faction_id) DO UPDATE SET
             name=excluded.name, is_current=excluded.is_current,
             knesset_num=excluded.knesset_num, start_date=excluded.start_date,
             finish_date=excluded.finish_date""",
        rows,
    )
    conn.commit()
    return len(rows)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    n_persons = load_persons(conn)
    n_factions = load_factions(conn)
    print(f"persons: {n_persons}  factions: {n_factions}  -> {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()

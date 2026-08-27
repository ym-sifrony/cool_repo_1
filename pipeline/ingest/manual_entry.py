"""Standing track for landmark quotes (spec.md: three L0 paths -- live forward
crawl via news_rss.py, telegram_scrape.py's own live/search modes, and this
one). Every entry here is a real quote a human found and verified by hand
against the live source, not something regex/llm pulled in.

RSS is genuinely forward-only (a feed only ever exposes its most recent
items), so a historically significant quote from a non-Telegram source (like
Lapid's 2022/2023 statements on קיצוני, both news sites) can only ever get in
through this file. Telegram is different -- t.me/s/<channel>?q=<term> searches
a channel's full archive, not just recent posts (verified live against
t.me/s/smutrich, which returned real posts from January 2024) -- so for a
REGISTERED Telegram channel, historical content could in principle be found
mechanically too, not only through this manual track. extraction_method is
'manual' here for exactly that reason -- there's no automated candidate to
review, a human already did that job by finding and citing the source
directly.

Not a one-off seed script anymore (it started as just Golan/Gantz, spec.md's
founding example) -- keep adding rows to CLAIMS/EVENTS below as more landmark
quotes are found. Re-running main() is safe (ON CONFLICT DO NOTHING).
"""
import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"
RETRIEVED_AT = "2026-08-26T00:00:00Z"


def checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


CLAIMS = [
    {
        "id": "clm_00001",
        "person_id": 30743,  # יאיר גולן
        "concept": "ציוני",
        "text_he": "מנסור עבאס יותר ציוני מסמוטריץ', יותר ציוני מבן גביר ויותר ציוני מהחרדים",
        "context_before": "בכנס יום הדמוקרטיה 2026 באוניברסיטת רייכמן, בשיח עם הסטודנט גיא שלום, אמר גולן:",
        "context_after": "",
        "claim_date": "2026-01-22",
        "source_medium": "text",
        "source_platform": "news_site",
        "source_url": "https://hamal.co.il/main/יאיר-גולן-בעיניי-239552",
        "source_locator": None,
    },
    {
        "id": "clm_00002",
        "person_id": 30657,  # בנימין גנץ
        "concept": "ציוני",
        "text_he": 'לבן גביר מצביעים ציוניים רבים, מנסור עבאס הוא לא ציוני',
        "context_before": "בתשובה לשאלת העיתונאי יהודה שלזינגר:",
        "context_after": "",
        "claim_date": "2026-01-19",
        "source_medium": "video",
        "source_platform": "instagram",
        "source_url": "https://www.instagram.com/p/DTsVSCNCv5I/",
        "source_locator": None,
    },
    {
        "id": "clm_00003",
        "person_id": 30686,  # מירב כהן
        "concept": "דמוקרטי",
        "text_he": "מפלגת הליכוד, במהלך לא מוסרי ולא דמוקרטי, ניסתה להקשות על קשישים בבתי אבות "
                   "לממש את זכותם הדמוקרטית ולהצביע בבחירות לכנסת.",
        "context_before": "",
        "context_after": "אחרי מאבק ציבורי ומשפטי נמצא מסלול עוקף שיאפשר בכל זאת להציב קלפיות בחלק מהמוסדות.",
        "claim_date": "2026-08-19",
        "source_medium": "video",
        "source_platform": "facebook",
        "source_url": "https://www.facebook.com/MeiravCohen2019/videos/2234264994078892/",
        "source_locator": None,
    },
    {
        # documentary only -- "הקיצונים" is a fuzzy group in this sentence, no event
        "id": "clm_00004",
        "person_id": 23594,  # יאיר לפיד
        "concept": "קיצוני",
        "text_he": "ניצחנו את הקיצונים בסיבוב הבחירות הקודם, ננצח אותם גם בסיבוב הבא",
        "context_before": "בכנס אלי הורביץ לכלכלה וחברה, מכון ישראלי לדמוקרטיה:",
        "context_after": "",
        "claim_date": "2022-06-22",
        "source_medium": "text",
        "source_platform": "news_site",
        "source_url": "https://www.c14.co.il/article/657950",
        "source_locator": None,
    },
    {
        # documentary only -- superlative over an unbounded universe, no event
        "id": "clm_00005",
        "person_id": 23594,  # יאיר לפיד
        "concept": "קיצוני",
        "text_he": "זה מה שקורה כשאתה מפקיד את המקום בידי האיש הכי קיצוני במדינת ישראל. "
                   "בן גביר רק מנסה להבעיר את המזרח התיכון",
        "context_before": "האירועים בהר הבית הם בגלל חוסר אחריות של הממשלה -",
        "context_after": "",
        "claim_date": "2023-04-09",
        "source_medium": "video",
        "source_platform": "x",
        "source_url": "https://x.com/ReshetBet/status/1644924077478404096",
        "source_locator": None,
    },
]

# Only comparisons/assignments naming a single resolvable person_id become events.
# "מהחרדים" (Golan) and "מצביעים ציוניים" (Gantz, about Ben Gvir's voters) name
# fuzzy groups, not a specific person/faction -- they stay documentary-only, per
# the tiered-universe rule in spec.md.
EVENTS = [
    {"id": "evt_00001", "claim_id": "clm_00001", "relation": "gt",
     "subject_id": "person:30713", "object_id": "person:30055", "concept": "ציוני"},  # עבאס > סמוטריץ'
    {"id": "evt_00002", "claim_id": "clm_00001", "relation": "gt",
     "subject_id": "person:30713", "object_id": "person:30811", "concept": "ציוני"},  # עבאס > בן גביר
    {"id": "evt_00003", "claim_id": "clm_00002", "relation": "not_in_class",
     "subject_id": "person:30713", "object_id": None, "concept": "ציוני"},           # עבאס לא ציוני
    {"id": "evt_00004", "claim_id": "clm_00003", "relation": "not_in_class",
     "subject_id": "faction:1096", "object_id": None, "concept": "דמוקרטי"},         # הליכוד לא דמוקרטי
    # (evidence of speaker's relation-structure, attached to the entity that performed
    # the described action -- per spec.md: an event need not assert a fact about the
    # entity, only reveal how the speaker structures the concept)
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)

    for c in CLAIMS:
        conn.execute(
            """INSERT INTO claims
               (id, person_id, concept, text_he, context_before, context_after,
                claim_date, source_medium, source_platform, source_url, source_locator,
                source_retrieved_at, source_checksum, source_status,
                extraction_method, extraction_confidence, reviewed_by)
               VALUES (:id, :person_id, :concept, :text_he, :context_before, :context_after,
                       :claim_date, :source_medium, :source_platform, :source_url, :source_locator,
                       :retrieved_at, :checksum, 'live',
                       'manual', 1.0, 'manual-seed-2026-08-26')
               ON CONFLICT(id) DO NOTHING""",
            {**c, "retrieved_at": RETRIEVED_AT, "checksum": checksum(c["text_he"])},
        )

    for e in EVENTS:
        conn.execute(
            """INSERT INTO events
               (id, claim_id, relation, subject_id, object_id, concept,
                extraction_method, extraction_confidence, reviewed_by)
               VALUES (:id, :claim_id, :relation, :subject_id, :object_id, :concept,
                       'manual', 1.0, 'manual-seed-2026-08-26')
               ON CONFLICT(id) DO NOTHING""",
            e,
        )

    conn.commit()
    print(f"claims: {len(CLAIMS)}  events: {len(EVENTS)}")
    conn.close()


if __name__ == "__main__":
    main()

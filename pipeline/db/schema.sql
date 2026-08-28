-- Reference tables (from Knesset OData, refreshed by pipeline/ingest/knesset_odata.py)

CREATE TABLE IF NOT EXISTS persons (
  person_id     INTEGER PRIMARY KEY,
  first_name    TEXT NOT NULL,
  last_name     TEXT NOT NULL,
  is_current    BOOLEAN NOT NULL,
  last_updated  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factions (
  faction_id    INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  is_current    BOOLEAN NOT NULL,
  knesset_num   INTEGER,
  start_date    TEXT,
  finish_date   TEXT
);

-- Telegram channel ownership -- manual verification only, never inferred.
-- A wrong mapping here means a quote gets attributed to the wrong speaker,
-- so every row must record how ownership was actually confirmed.
CREATE TABLE IF NOT EXISTS telegram_channel_registry (
  person_id          INTEGER NOT NULL REFERENCES persons(person_id),
  channel_username   TEXT NOT NULL,
  verification_note  TEXT NOT NULL,
  verification_url   TEXT NOT NULL,
  verified_by         TEXT NOT NULL,
  verified_at          TEXT NOT NULL,
  is_active             BOOLEAN NOT NULL DEFAULT 1,
  PRIMARY KEY (person_id, channel_username)
);

-- L1: claims (documentary record; every row requires a source)

CREATE TABLE IF NOT EXISTS claims (
  id                  TEXT PRIMARY KEY,
  person_id           INTEGER NOT NULL REFERENCES persons(person_id),
  concept             TEXT NOT NULL,
  concept_grammatical_form TEXT CHECK(concept_grammatical_form IN ('noun','adjective','mixed')),
  text_he             TEXT NOT NULL,
  context_before      TEXT NOT NULL,
  context_after       TEXT NOT NULL,
  claim_date          TEXT NOT NULL,
  source_medium       TEXT NOT NULL CHECK(source_medium IN ('text','video','audio')),
  source_platform     TEXT NOT NULL,
  source_url          TEXT NOT NULL,
  source_locator       TEXT,
  source_retrieved_at  TEXT NOT NULL,
  source_checksum      TEXT NOT NULL,
  source_archive_url    TEXT,
  source_local_copy     TEXT,
  source_status         TEXT NOT NULL DEFAULT 'live',
  source_status_checked_at TEXT,
  extraction_method     TEXT NOT NULL CHECK(extraction_method IN ('manual','regex','llm')),
  extraction_confidence  REAL,
  reviewed_by            TEXT,
  -- Separate from `approved` (candidates.json -> claims gate, "is this
  -- accurately extracted"): visible governs "should this show on the public
  -- site". A claim can be accurate AND deliberately not shown yet (e.g. an
  -- "unclear"-bucket claim a curator judges confusing without more context)
  -- -- default true, never silently drops a sourced record either way.
  visible                BOOLEAN NOT NULL DEFAULT 1
);

-- Static relationships between the CONCEPTS themselves (vocabulary-level,
-- curated by hand) -- distinct from events.relation, which records what a
-- SPEAKER asserted about specific entities for one concept. This table never
-- feeds a classification; it's descriptive metadata about the concept list
-- (e.g. "טוב"/"רע" are antonyms), useful for grouping/UI, not for judging
-- consistency.
CREATE TABLE IF NOT EXISTS concept_relations (
  concept_a   TEXT NOT NULL,
  concept_b   TEXT NOT NULL,
  relation    TEXT NOT NULL CHECK(relation IN ('antonym','synonym','related')),
  note        TEXT,
  PRIMARY KEY (concept_a, concept_b, relation),
  CHECK (concept_a < concept_b)
);

-- L2.1: events (structured comparisons/assignments parsed out of a claim; graph edges)

CREATE TABLE IF NOT EXISTS events (
  id                  TEXT PRIMARY KEY,
  claim_id            TEXT NOT NULL REFERENCES claims(id),
  relation            TEXT NOT NULL CHECK(relation IN ('gt','eq_ordinal','in_class','not_in_class','anti_class')),
  subject_id           TEXT NOT NULL,
  object_id             TEXT,
  concept                TEXT NOT NULL,
  extraction_method       TEXT NOT NULL CHECK(extraction_method IN ('manual','regex','llm')),
  extraction_confidence    REAL,
  reviewed_by               TEXT
);

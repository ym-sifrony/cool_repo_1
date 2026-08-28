"""Mechanical detection of concept_grammatical_form (spec.md L2.1): noun vs
adjective, via syntactic tests -- never semantic interpretation.

  1. Comparative attachment: "יותר [concept]" or "[concept] יותר" -> adjective
     (both orders); "[concept] [other-word] יותר" -> noun (יותר attaches to
     the OTHER word).
  2. Morphological agreement: [concept] inflected to agree in number/gender
     with a preceding noun it modifies -> adjective. Includes construct-plural
     group heads ("אנשי X", two words back, not the directly-adjacent word)
     and gendered-singular agreement ("מדינה נורמלית").
  3. Preposition-headed plural ("לחכמים", "מהדמוקרטים") -> noun: a preposition
     attaches to a noun phrase, so a plural concept-form directly carrying one
     is nominalized regardless of what precedes it.
  4. Definite article, standalone after "את"/clause-start -> noun (nominalized
     category, not agreement with a modifiable preceding noun).
  5. Bare predicative fallback ("הוא/אינו + [concept]", no comparison): noun
     by declared convention (spec.md L2.1), not derived.

Everything this can't resolve returns None ("ambiguous") -- automated output,
always routed to human review before it affects any claim record.
"""
import re
from dataclasses import dataclass

NEGATION_WORDS = {"לא", "אינו", "אינה", "אינם", "אינן"}
COPULA_WORDS = {"הוא", "היא", "הם", "הן"}
PLURAL_SUFFIXES = ("ים", "ות")

# Construct-plural (סמיכות) head nouns for politically-relevant GROUPS --
# "אנשי מקצוע ציוניים" agrees with "אנשי" (people-of), two words back, not
# with the directly-preceding "מקצוע" (profession, singular). Construct
# plurals end in "-י", not "-ים"/"-ות", so PLURAL_SUFFIXES can't see them
# either way. Deliberately scoped to group/political-actor nouns, not
# general Hebrew construct-state parsing -- found on real registered-channel
# data, expected to grow as more real examples turn up (spec.md's own
# "gilui munah-netunim" principle: expand from data, not upfront guessing).
CONSTRUCT_PLURAL_HEADS = {
    "אנשי", "חברי", "ראשי", "נציגי", "תומכי", "פעילי", "בוחרי",
    "מנהיגי", "עסקני", "שרי", "בני",
}


SOFIT_TO_REGULAR = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}

# Abstract/quality noun for each concept -- e.g. "אידיאולוגי" (adjective) vs
# "אידיאולוגיה" (the noun, ideology). Deliberately NOT derived by a suffix
# rule the way plural/gender inflection above is: some concepts really are
# "stem+יות" (already covered by inflected_forms, e.g. מוסרי->מוסריות --
# listing those here too would be redundant, so they're left out), some take
# the borrowed "-יה" pattern inflected_forms never generates (דמוקרטי-
# >דמוקרטיה, אידיאולוגי->אידיאולוגיה), and some are fully irregular
# (חופשי->חופש, ציוני->ציונות not the auto-generated "ציוניות"). Verified by
# hand per concept, same "gilui munah-netunim" principle as
# CONSTRUCT_PLURAL_HEADS -- expanded from real data, not guessed morphology.
ABSTRACT_NOUN_FORMS: dict[str, str] = {
    "ציוני": "ציונות",
    "חופשי": "חופש",
    "דמוקרטי": "דמוקרטיה",
    "אידיאולוגי": "אידיאולוגיה",
    "גזעני": "גזענות",
    "לאומני": "לאומנות",
    "מתון": "מתינות",
    "ישר": "יושר",
    "יהודי": "יהדות",
    "זהותי": "זהות",
    "מושחת": "שחיתות",
    "צודק": "צדק",
    # "ימין"/"שמאל" also mean physical direction, so this trades precision
    # for recall -- accepted deliberately, same as load_persons' wider-pool
    # tradeoff (grammatical_form.py, quote_extractor.py): real political
    # discourse overwhelmingly uses these as the camp-noun with a glued
    # prefix ("שבימין", "אנשי השמאל", "ממפלגות השמאל" -- all real quotes
    # found and previously invisible to find_occurrences entirely, since
    # PREFIX_CHARS handling only helps once the base form itself is known).
    # Human review in review_queue/candidates.json is the actual safeguard.
    "ימני": "ימין",
    "שמאלי": "שמאל",
}


def _regularize_final_letter(stem: str) -> str:
    """Hebrew final-letter forms (ך/ם/ן/ף/ץ) are only valid at the actual end
    of a word -- appending a suffix moves that letter to a non-final position,
    so it must convert to its regular form first (e.g. "נאמן" + "ה" needs to
    be "נאמנה", not the non-word "נאמןה" naive concatenation would produce).
    Found by auditing every concept's generated forms, not a hypothetical:
    "נאמן" was effectively unsearchable in any inflected form because of this."""
    if stem and stem[-1] in SOFIT_TO_REGULAR:
        return stem[:-1] + SOFIT_TO_REGULAR[stem[-1]]
    return stem


def inflected_forms(base: str) -> list[str]:
    """Plausible surface forms of a masc.sg. Hebrew adjective (mechanical, not
    a full morphological analyzer)."""
    forms = {base}
    if base.endswith("י"):
        stem = _regularize_final_letter(base[:-1])
        # both "ים"/"יים" plurals occur in real usage (e.g. קיצונים AND קיצוניים)
        forms |= {stem + "ית", stem + "יים", stem + "יות", stem + "ים"}
    elif base.endswith("ון"):
        stem = _regularize_final_letter(base[:-2])
        forms |= {stem + "ונה", stem + "ונים", stem + "ונות"}
    else:
        # both suffixes generated regardless of which is "real" for this
        # specific word (e.g. "צודק" needs "צודקת", not the "צודקה" a plain
        # "+ה" rule would give -- it's a פועל-pattern participle, not a plain
        # adjective like "נאמן"/"ישר"). The wrong one just never matches real
        # text ("נאמנת" isn't a word), so over-generating here is free.
        stem = _regularize_final_letter(base)
        forms |= {stem + "ה", stem + "ת", stem + "ים", stem + "ות"}
    return sorted(forms, key=len, reverse=True)


@dataclass
class Occurrence:
    matched_text: str
    position: int
    form: str | None  # "noun" | "adjective" | None (ambiguous)
    reason: str


# Hebrew prefix letters that attach directly to a word with no space
# (conjunction/prepositions/definite article: ו/ב/כ/ל/מ/ש/ה, incl. combos like "ול", "שה").
PREFIX_CHARS = "ובכלמשה"


def _strip_prefix(word: str, target: str) -> bool:
    """True if `word` is `target` with 0-3 Hebrew prefix letters glued to the front."""
    if not word.endswith(target):
        return False
    prefix = word[: -len(target)] if target else word
    return len(prefix) <= 3 and all(ch in PREFIX_CHARS for ch in prefix)


def find_occurrences(text: str, concept: str) -> list[Occurrence]:
    abstract_noun = ABSTRACT_NOUN_FORMS.get(concept)
    forms = inflected_forms(concept)
    if abstract_noun and abstract_noun not in forms:
        forms = sorted({*forms, abstract_noun}, key=len, reverse=True)
    # allow up to 3 glued prefix letters before the concept form itself (ה/ו/ב/כ/ל/מ/ש)
    pattern = re.compile(
        r"(?<!\S)([" + PREFIX_CHARS + r"]{0,3})(" + "|".join(re.escape(f) for f in forms)
        + r")(?=[\s,.;:!?\"'׳״)\]-]|$)"
    )

    results = []
    for match in pattern.finditer(text):
        start, end = match.span()
        before_words = text[:start].split()
        after_words = text[end:].split()
        before_word = before_words[-1] if before_words else ""
        prefix, matched_word = match.group(1), match.group(2)

        # The abstract noun is a distinct word, not a context-dependent
        # inflection of the adjective -- it's always a noun regardless of
        # what precedes it (unlike, say, "יותר" which normally signals the
        # adjective form). Must come before the comparative check below, or
        # "יותר דמוקרטיה" (more democracy, a noun) would be mistagged
        # adjective the same way "יותר דמוקרטי" (more democratic) is.
        if matched_word == abstract_noun:
            results.append(Occurrence(matched_word, start, "noun",
                                       "curated abstract/quality noun form of the concept"))
            continue

        if _strip_prefix(before_word, "יותר") or _strip_prefix(before_word, "הכי"):
            results.append(Occurrence(matched_word, start, "adjective",
                                       f"comparative marker attaches directly ('{before_word}')"))
            continue
        # post-modifier comparative: "צודק יותר" (more correct) is the same
        # comparison as "יותר צודק", just with יותר AFTER the concept instead
        # of before it -- both orders are standard Hebrew, only one was
        # handled (found by testing "צודק יותר" against the code directly).
        if after_words and _strip_prefix(after_words[0], "יותר"):
            results.append(Occurrence(matched_word, start, "adjective",
                                       f"comparative marker attaches directly, post-modifier ('{after_words[0]}')"))
            continue
        if len(after_words) >= 2 and _strip_prefix(after_words[1], "יותר"):
            results.append(Occurrence(matched_word, start, "noun",
                                       "יותר attaches to a following word, not the concept"))
            continue

        p_plural = before_word.endswith(PLURAL_SUFFIXES)
        c_plural = matched_word.endswith(PLURAL_SUFFIXES)
        is_negation_or_copula = any(
            _strip_prefix(before_word, w) for w in NEGATION_WORDS | COPULA_WORDS
        )
        construct_head = before_words[-2] if len(before_words) >= 2 else None
        p_construct_plural = construct_head in CONSTRUCT_PLURAL_HEADS
        if before_word and not is_negation_or_copula and c_plural and (p_plural or p_construct_plural):
            reason = (f"agrees in number with preceding '{before_word}'" if p_plural else
                      f"agrees in number with construct-plural head '{construct_head} {before_word}'")
            results.append(Occurrence(matched_word, start, "adjective", reason))
            continue

        # preposition-headed plural: ב/כ/ל/מ (with or without glued "ה")
        # directly on a PLURAL concept-form is reliably nominal -- a
        # preposition attaches to a noun phrase, and Hebrew regularly
        # nominalizes plural adjectives this way ("לחכמים", "מהדמוקרטים",
        # "ליהודים") even with no definite article at all. Generalizes the
        # "ה"-nominalization rule below to also cover a preceding proper name
        # (which structurally can't take an adjective modifier in the first
        # place) -- found on real registered-channel data, not hypothetical.
        if c_plural and any(ch in "בכלמ" for ch in prefix):
            results.append(Occurrence(matched_word, start, "noun",
                                       f"preposition-headed plural ('{prefix}{matched_word}') -> nominalized"))
            continue

        # Plural agreement (above) is the RARER case -- most nouns appear in
        # singular. A gendered-singular inflection (e.g. "נורמלית", not the
        # bare masc. base "נורמלי" and not a plural) modifying a preceding
        # word is the far more common adjective pattern ("מדינה נורמלית")
        # and previously fell through every rule to "ambiguous" (a real gap,
        # found by testing real seeded quotes -- not a hypothetical).
        is_gendered_singular_form = matched_word != concept and not c_plural
        if before_word and not is_negation_or_copula and is_gendered_singular_form:
            results.append(Occurrence(matched_word, start, "adjective",
                                       f"gendered singular form agrees with preceding '{before_word}'"))
            continue

        # narrow on purpose: "ה" alone doesn't mean nominalization -- an adjective
        # modifying a definite noun also takes "ה" ("זכותם הדמוקרטית"). Only fire
        # when the preceding word structurally cannot be a noun the concept modifies:
        # the direct-object marker "את", or nothing (clause start).
        cannot_be_modifying_a_noun = not before_word or _strip_prefix(before_word, "את")
        if "ה" in prefix and cannot_be_modifying_a_noun:
            results.append(Occurrence(matched_word, start, "noun",
                                       "definite article, standalone after 'את'/clause-start "
                                       "-> nominalized, stands as its own category"))
            continue

        if is_negation_or_copula:
            results.append(Occurrence(matched_word, start, "noun",
                                       f"bare predicative after '{before_word}' (convention, not derived)"))
            continue

        results.append(Occurrence(matched_word, start, None, "no test matched"))

    return results


def claim_level_form(occurrences: list[Occurrence]) -> str | None:
    """Reduce all occurrences in one claim to a single field (spec.md accepted
    this as a simplification -- 'mixed' when the claim genuinely contains both)."""
    forms = {o.form for o in occurrences if o.form is not None}
    if not forms:
        return None
    if len(forms) == 1:
        return forms.pop()
    return "mixed"

"""Mechanical detection of concept_grammatical_form (spec.md L2.1): noun vs
adjective, via two syntactic tests -- never semantic interpretation.

  1. Comparative attachment: "יותר [concept]" -> adjective;
     "[concept] [other-word] יותר" -> noun (יותר attaches to the OTHER word).
  2. Morphological agreement: [concept] inflected to agree in number/gender
     with an immediately preceding noun it modifies -> adjective.
  3. Bare predicative fallback ("הוא/אינו + [concept]", no comparison): noun
     by declared convention (spec.md L2.1), not derived.

Everything this can't resolve returns None ("ambiguous") -- automated output,
always routed to human review before it affects any claim record.
"""
import re
from dataclasses import dataclass

NEGATION_WORDS = {"לא", "אינו", "אינה", "אינם", "אינן"}
COPULA_WORDS = {"הוא", "היא", "הם", "הן"}
PLURAL_SUFFIXES = ("ים", "ות")


def inflected_forms(base: str) -> list[str]:
    """Plausible surface forms of a masc.sg. Hebrew adjective (mechanical, not
    a full morphological analyzer)."""
    forms = {base}
    if base.endswith("י"):
        stem = base[:-1]
        # both "ים"/"יים" plurals occur in real usage (e.g. קיצונים AND קיצוניים)
        forms |= {stem + "ית", stem + "יים", stem + "יות", stem + "ים"}
    elif base.endswith("ון"):
        stem = base[:-2]
        forms |= {stem + "ונה", stem + "ונים", stem + "ונות"}
    else:
        # both suffixes generated regardless of which is "real" for this
        # specific word (e.g. "צודק" needs "צודקת", not the "צודקה" a plain
        # "+ה" rule would give -- it's a פועל-pattern participle, not a plain
        # adjective like "נאמן"/"ישר"). The wrong one just never matches real
        # text ("נאמנת" isn't a word), so over-generating here is free.
        forms |= {base + "ה", base + "ת", base + "ים", base + "ות"}
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
    forms = inflected_forms(concept)
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
        if before_word and not is_negation_or_copula and p_plural and c_plural:
            results.append(Occurrence(matched_word, start, "adjective",
                                       f"agrees in number with preceding '{before_word}'"))
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

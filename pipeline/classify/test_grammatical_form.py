"""Tests for grammatical_form.py against real sentences found while working
this session -- not synthetic. Every case here was a sentence a human would
classify unambiguously, checked against what the code actually returned
(spec.md L2, "שני צירים בלתי-תלויים").
"""
import unittest

from grammatical_form import find_occurrences


def forms(text, concept):
    return [(o.matched_text, o.form) for o in find_occurrences(text, concept)]


class TestComparative(unittest.TestCase):
    def test_more_X_is_adjective(self):
        self.assertEqual(
            forms("עבאס יותר ציוני מסמוטריץ", "ציוני"),
            [("ציוני", "adjective")],
        )

    def test_most_X_is_adjective(self):
        self.assertEqual(
            forms("האיש הכי קיצוני במדינת ישראל", "קיצוני"),
            [("קיצוני", "adjective")],
        )

    def test_post_modifier_more_is_also_adjective(self):
        # "צודק יותר" (more correct) is the same comparison as "יותר צודק",
        # just with יותר AFTER the concept -- both orders are standard
        # Hebrew, only the pre-modifier order was originally handled.
        self.assertEqual(
            forms("צודק יותר", "צודק"),
            [("צודק", "adjective")],
        )


class TestBarePredicative(unittest.TestCase):
    def test_negation_is_noun_by_convention(self):
        self.assertEqual(
            forms("היא לא דמוקרטית", "דמוקרטי"),
            [("דמוקרטית", "noun")],
        )


class TestDefiniteNominalization(unittest.TestCase):
    def test_et_ha_X_is_noun(self):
        self.assertEqual(
            forms("ניצחנו את הקיצונים", "קיצוני"),
            [("קיצונים", "noun")],
        )


class TestGenderedSingularAgreement(unittest.TestCase):
    """The bug this session actually found: real quotes like "מדינה נורמלית"
    (Hamad Amar, Maariv 2023-05-22) returned None ("ambiguous") because the
    only agreement rule that existed checked PLURAL suffix agreement -- but
    singular is the far more common case in real speech."""

    def test_state_normal_singular_feminine_agreement(self):
        self.assertEqual(
            forms("אנחנו לא מדינה נורמלית", "נורמלי"),
            [("נורמלית", "adjective")],
        )

    def test_definite_noun_with_agreeing_adjective_not_nominalized(self):
        # spec.md's own worked example: "ה" here is required agreement with
        # a definite noun ("her right"), NOT nominalization -- must stay
        # adjective, not fall through to "noun" or "ambiguous".
        self.assertEqual(
            forms("זכותה הדמוקרטית", "דמוקרטי"),
            [("דמוקרטית", "adjective")],
        )

    def test_paradox_sentence_mixes_adjective_and_bare_predicative(self):
        # "a normal state that isn't normal" -- first occurrence modifies
        # "מדינה" (adjective), second is bare predicative after "שאינה"
        # (noun by convention). Same sentence, two different forms.
        self.assertEqual(
            forms("מדינה נורמלית שאינה נורמלית", "נורמלי"),
            [("נורמלית", "adjective"), ("נורמלית", "noun")],
        )

    def test_negation_still_wins_over_gendered_form(self):
        # the gendered-singular rule must not override the negation rule --
        # "היא לא דמוקרטית" (tested above) already covers masc/fem-neutral
        # phrasing; this checks the new rule's own negation guard directly.
        result = forms("זו לא נורמלית", "נורמלי")
        self.assertEqual(result, [("נורמלית", "noun")])


class TestConstructPluralHead(unittest.TestCase):
    def test_anshei_miktzoa_tzioniim(self):
        # "אנשי מקצוע ציוניים" -- the concept agrees with "אנשי" (people-of),
        # two words back, not the directly-adjacent "מקצוע" (profession,
        # singular). Found on a real registered official Telegram channel's
        # post (Smotrich), not synthetic.
        self.assertEqual(
            forms("נציב אנשי מקצוע ציוניים בעמדות המפתח", "ציוני"),
            [("ציוניים", "adjective")],
        )


class TestPrepositionHeadedPluralNoun(unittest.TestCase):
    def test_layehudim_is_nominal_group_reference(self):
        # "ליהודים" (to/for Jews) -- no definite article at all, just a bare
        # plural after a preposition, but still reliably a nominal group
        # reference, not an adjective. Real sentence from Smotrich's channel.
        self.assertEqual(
            forms("יש ביטחון ליהודים", "יהודי"),
            [("יהודים", "noun")],
        )

    def test_mehademokratim_preceded_by_a_name_not_a_noun(self):
        # "מהדמוקרטים" (from the Democrats) -- preceded by a proper name
        # ("רדמן"), which structurally can't take an adjective modifier at
        # all, so the old "ה"-nominalization rule's cannot_be_modifying_a_noun
        # guard (only את/clause-start) wrongly missed this. Real sentence.
        self.assertEqual(
            forms("תקשיבו למשה רדמן מהדמוקרטים", "דמוקרטי"),
            [("דמוקרטים", "noun")],
        )


class TestSofitLetterRegularization(unittest.TestCase):
    def test_neeman_feminine_form_uses_regular_not_final_nun(self):
        # naive concatenation gives "נאמןה" (keeps sofit ן mid-word, not a
        # real word) instead of "נאמנה" -- found by auditing every one of
        # the 24 approved concepts' generated forms, not a hypothetical.
        # "נאמן" was effectively unsearchable in any inflected form at all
        # before this fix.
        self.assertEqual(
            forms("ידידות נאמנה", "נאמן"),
            [("נאמנה", "adjective")],
        )

    def test_neeman_plural_also_regularized(self):
        self.assertEqual(
            forms("חברים נאמנים", "נאמן"),
            [("נאמנים", "adjective")],
        )


class TestParticipleFeminineForm(unittest.TestCase):
    def test_tzodeket_not_tzodeka(self):
        # "צודק" is a פועל-pattern participle (correct/right) -- its real
        # feminine form takes ת ("צודקת"), not the generic "+ה" rule's
        # "צודקה", which isn't a real word. Without this, "הכי צודקת" was
        # never even found by the regex, let alone classified.
        self.assertEqual(
            forms("הכי צודקת", "צודק"),
            [("צודקת", "adjective")],
        )


if __name__ == "__main__":
    unittest.main()

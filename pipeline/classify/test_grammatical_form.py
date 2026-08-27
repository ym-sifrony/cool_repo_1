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


if __name__ == "__main__":
    unittest.main()

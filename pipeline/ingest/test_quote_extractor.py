"""Tests for quote_extractor.py's locate stage -- finding a quote span and
resolving WHO said it. Deliberately narrow in scope (module docstring,
extract_candidates): only direct, mechanical attribution (name/pronoun
touching the quote, or an unbroken carry-forward chain) resolves a speaker.
Anything that needs to read the article's broader context to figure out the
speaker belongs to a later, separate interpretation stage -- not guessed
here. Real sentences, not synthetic (same convention as test_grammatical_form.py).
"""
import unittest

from quote_extractor import extract_candidates

NAME_TO_ID = {"יאיר גולן": 1, "אביגדור ליברמן": 2, "בצלאל סמוטריץ": 3}
CONCEPTS = ["ציוני", "ימני"]


def extract(text):
    return extract_candidates(text, "http://x", "title", "2024-01-01", "web",
                               NAME_TO_ID, CONCEPTS)


class TestDocumentedPatterns(unittest.TestCase):
    def test_attr_before_quote_with_verb(self):
        c = extract('יאיר גולן אמר: "מנסור עבאס יותר ציוני מסמוטריץ"')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("יאיר גולן", "ציוני")])

    def test_attr_before_quote_no_verb(self):
        c = extract('יאיר גולן: "מנסור עבאס יותר ציוני מסמוטריץ"')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("יאיר גולן", "ציוני")])

    def test_quote_then_attr(self):
        c = extract('"מנסור עבאס יותר ציוני מסמוטריץ" אמר יאיר גולן.')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("יאיר גולן", "ציוני")])

    def test_quote_then_attr_with_kach_connector(self):
        # "— כך אמר X" -- documented in the module docstring but never
        # actually matched before this fix: [\s,—-]* doesn't cover the
        # letters כ/ך, so "כך" blocked the verb match entirely.
        c = extract('"מנסור עבאס יותר ציוני מסמוטריץ" — כך אמר יאיר גולן.')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("יאיר גולן", "ציוני")])


class TestPresentTenseVerb(unittest.TestCase):
    def test_mesaber_present_tense(self):
        # Real gap: SPEECH_VERBS only had past-tense forms ("אמר"), never
        # present/benoni ("מסביר") -- found on a real article (Lieberman,
        # Maariv 2021-03-20) that used only "מסביר" and matched nothing.
        c = extract('אביגדור ליברמן: "מנסור עבאס יותר ציוני מסמוטריץ", הוא מסביר.')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("אביגדור ליברמן", "ציוני")])

    def test_hidgish_verb(self):
        # Real headline (Haaretz, 2026-05-01): "'אני ימני', הדגיש בנט" --
        # "הדגיש" wasn't in SPEECH_VERBS at all before this.
        c = extract('"מנסור עבאס יותר ציוני מסמוטריץ", הדגיש יאיר גולן.')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("יאיר גולן", "ציוני")])


class TestBareSurname(unittest.TestCase):
    def test_verb_then_surname_before_quote(self):
        # Real headline (Haaretz, 2026-05-01): "'אני ימני', הדגיש בנט" also
        # exposed this in the after-quote direction; this is the mirrored
        # before-quote order. Without ATTR_BEFORE_VERB_NAME checked first,
        # ATTR_BEFORE_NAME's optional second-word slot swallows the verb
        # itself as if "אמר ליברמן" were a two-word name.
        c = extract('בריאיון אמר ליברמן: "מנסור עבאס יותר ציוני מסמוטריץ"')
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("אביגדור ליברמן", "ציוני")])

    def test_real_lieberman_on_smotrich(self):
        # Real quote, Maariv 2021-03-20: "סמוטריץ' הוא לא ימני, הוא פנטי".
        c = extract('בריאיון האחרון שלו אמר ליברמן: "סמוטריץ הוא לא ימני, הוא פנטי". זו הייתה אמירה חדה')
        self.assertEqual(
            [(x.attributed_name, x.concept, x.concept_grammatical_form) for x in c],
            [("אביגדור ליברמן", "ימני", "noun")],
        )

    def test_ambiguous_surname_resolves_to_nothing(self):
        # "גולן" alone fits two different tracked people -- must NOT guess
        # which one; disambiguating from context is an interpretation-stage
        # concern (see resolve_speaker's docstring), not this stage's job.
        ambiguous_names = {**NAME_TO_ID, "משה גולן": 4}
        c = extract_candidates(
            'אמר גולן: "מנסור עבאס יותר ציוני מסמוטריץ"',
            "http://x", "title", "2024-01-01", "web", ambiguous_names, CONCEPTS,
        )
        self.assertEqual(c, [])


class TestPronounAndCarryForward(unittest.TestCase):
    def test_pronoun_after_established_speaker(self):
        # Second sentence has no name at all, only "הוא מסביר" -- must
        # resolve against the speaker established by the first sentence.
        c = extract(
            'אביגדור ליברמן אמר: "דבר ראשון." '
            '"מנסור עבאס יותר ציוני מסמוטריץ", הוא מסביר.'
        )
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("אביגדור ליברמן", "ציוני")])

    def test_consecutive_quote_with_zero_attribution_carries_forward(self):
        # Real pattern (same Lieberman article): a second quote directly
        # abutting the first, with NO attribution touching it at all --
        # attributed once, inherited by every quote in the run.
        c = extract(
            'אביגדור ליברמן אמר: "דבר ראשון." '
            '"מנסור עבאס יותר ציוני מסמוטריץ."'
        )
        self.assertEqual([(x.attributed_name, x.concept) for x in c], [("אביגדור ליברמן", "ציוני")])

    def test_unresolved_named_attribution_breaks_the_chain(self):
        # A real, different, untracked speaker interrupts -- a LATER
        # pronoun-only quote must NOT be wrongly inherited from before the
        # interruption.
        c = extract(
            'אביגדור ליברמן אמר: "דבר ראשון." '
            'עיתונאי אלמוני הוסיף: "הערה לא קשורה." '
            '"מנסור עבאס יותר ציוני מסמוטריץ", הוא מסביר.'
        )
        self.assertEqual(c, [])


if __name__ == "__main__":
    unittest.main()

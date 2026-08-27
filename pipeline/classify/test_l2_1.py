"""Synthetic tests for the L2.1 classifier's pure functions (spec.md section 3.6).
Not testing against real seeded data -- constructing minimal cases that must and
must not trigger each classification, especially "inconsistent", which nothing
in the real seed data exercises yet.
"""
import unittest

from l2_1 import classify_equivalence, classify_group, classify_order


def ev(relation, subject_id, object_id=None, event_id="e"):
    return {"relation": relation, "subject_id": subject_id,
            "object_id": object_id, "event_id": event_id}


class TestOrder(unittest.TestCase):
    def test_single_edge_on_two_entities_is_trivially_total(self):
        # universe={a,b} has exactly one possible pair, and it was compared --
        # this is genuinely total, just not a meaningful one (matches spec.md's
        # note that "not comparable" only becomes possible once n>=3).
        result = classify_order([ev("gt", "a", "b", "e1")])
        self.assertEqual(result["classification"], "strict_order_total")
        self.assertEqual(result["violations"], [])

    def test_missing_pair_among_three_is_partial(self):
        # matches Golan's real data shape: abbas>smotrich, abbas>bengvir,
        # but smotrich-vs-bengvir was never compared.
        events = [ev("gt", "abbas", "smotrich", "e1"),
                  ev("gt", "abbas", "bengvir", "e2")]
        result = classify_order(events)
        self.assertEqual(result["classification"], "strict_order_partial")
        self.assertEqual(result["violations"], [])

    def test_direct_contradiction_is_caught(self):
        events = [ev("gt", "a", "b", "e1"), ev("gt", "b", "a", "e2")]
        result = classify_order(events)
        self.assertEqual(result["classification"], "inconsistent")
        self.assertEqual(len(result["violations"]), 1)
        self.assertEqual(result["violations"][0]["conflicting_event"], "e2")

    def test_tie_is_not_a_contradiction(self):
        events = [ev("eq_ordinal", "a", "b", "e1"), ev("gt", "a", "c", "e2")]
        result = classify_order(events)
        self.assertEqual(result["classification"], "weak_order")
        self.assertEqual(result["violations"], [])

    def test_all_pairs_compared_is_total(self):
        events = [ev("gt", "a", "b", "e1"), ev("gt", "b", "c", "e2"),
                  ev("gt", "a", "c", "e3")]
        result = classify_order(events)
        self.assertEqual(result["classification"], "strict_order_total")

    def test_duplicate_same_direction_is_not_a_violation(self):
        events = [ev("gt", "a", "b", "e1"), ev("gt", "a", "b", "e2"),
                  ev("gt", "a", "c", "e3")]
        result = classify_order(events)
        self.assertEqual(result["classification"], "strict_order_partial")
        self.assertEqual(result["violations"], [])


class TestEquivalence(unittest.TestCase):
    def test_disjoint_assignments_are_fine(self):
        events = [ev("in_class", "a", event_id="e1"),
                  ev("not_in_class", "b", event_id="e2")]
        result = classify_equivalence(events)
        self.assertEqual(result["classification"], "equivalence")
        self.assertEqual(result["violations"], [])

    def test_same_entity_both_polarities_is_caught(self):
        events = [ev("in_class", "a", event_id="e1"),
                  ev("not_in_class", "a", event_id="e2")]
        result = classify_equivalence(events)
        self.assertEqual(result["classification"], "inconsistent")
        self.assertEqual(len(result["violations"]), 1)
        self.assertEqual(
            result["violations"][0]["conflicting_events"], ["e1", "e2"]
        )

    def test_same_entity_same_polarity_twice_is_fine(self):
        events = [ev("not_in_class", "a", event_id="e1"),
                  ev("not_in_class", "a", event_id="e2")]
        result = classify_equivalence(events)
        self.assertEqual(result["classification"], "equivalence")
        self.assertEqual(result["violations"], [])


class TestGroupRouting(unittest.TestCase):
    def test_empty_is_no_discourse(self):
        result = classify_group([])
        self.assertEqual(result["classification"], "no_discourse")

    def test_majority_comparative_routes_to_order(self):
        events = [ev("gt", "a", "b", "e1"), ev("gt", "a", "c", "e2"),
                  ev("in_class", "a", event_id="e3")]
        result = classify_group(events)
        self.assertIn(result["classification"],
                       {"strict_order_total", "strict_order_partial", "weak_order"})


if __name__ == "__main__":
    unittest.main()

"""L2.1 relation-structure classifier (spec.md section 3.6).

For each (speaker, concept, grammatical_form) bucket, builds a graph from that
speaker's events and checks it against the formal taxonomy: equivalence,
strict_order_total/partial, weak_order, no_discourse, inconsistent,
mixed_relation_types.

Two independent axes, never conflated:
  - grammatical_form (noun/adjective) is read straight from the claim -- syntax.
  - classification (order/equivalence/...) is computed empirically from the graph
    -- semantics. Grammar never determines the answer, only which bucket to test.
"""
import sqlite3
from collections import defaultdict
from pathlib import Path

import networkx as nx

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "concepts.db"

ORDER_RELATIONS = {"gt", "eq_ordinal"}
# not_in_class ("not X") and anti_class ("anti-X") are kept distinct on purpose --
# "anti-X" is not derived automatically from "not X", it requires a human to judge
# the speaker actually treats it as its own class (spec.md L1 event-creation rules),
# never inferred mechanically. See classify_equivalence for what that buys us.
EQUIVALENCE_RELATIONS = {"in_class", "not_in_class", "anti_class"}


def fetch_event_groups(conn: sqlite3.Connection) -> dict:
    """Group events by (speaker person_id, concept, grammatical_form)."""
    rows = conn.execute(
        """SELECT c.person_id, e.concept, c.concept_grammatical_form,
                  e.relation, e.subject_id, e.object_id, e.id
           FROM events e JOIN claims c ON c.id = e.claim_id"""
    ).fetchall()

    groups = defaultdict(list)
    for person_id, concept, form, relation, subject_id, object_id, event_id in rows:
        key = (person_id, concept, form or "unknown")
        groups[key].append(
            {"relation": relation, "subject_id": subject_id,
             "object_id": object_id, "event_id": event_id}
        )
    return groups


def classify_order(events: list[dict]) -> dict:
    """Antisymmetry + totality check on gt/eq_ordinal events (spec.md 3.6)."""
    graph = nx.DiGraph()
    ties = set()
    violations = []
    universe = set()

    for e in events:
        universe.add(e["subject_id"])
        universe.add(e["object_id"])

    for e in events:
        a, b = e["subject_id"], e["object_id"]
        if e["relation"] == "eq_ordinal":
            ties.add(frozenset((a, b)))
            continue
        if graph.has_edge(b, a):  # reverse already asserted -> direct contradiction
            violations.append({"pair": (a, b), "conflicting_event": e["event_id"]})
            continue
        graph.add_edge(a, b)

    if violations:
        classification = "inconsistent"
    else:
        n = len(universe)
        max_pairs = n * (n - 1) // 2
        compared_pairs = {frozenset(edge) for edge in graph.edges()} | ties
        if ties:
            classification = "weak_order"
        elif len(compared_pairs) >= max_pairs:
            classification = "strict_order_total"
        else:
            classification = "strict_order_partial"

    return {"classification": classification, "universe": sorted(universe),
            "violations": violations}


def classify_equivalence(events: list[dict]) -> dict:
    """No entity assigned to two different classes -- N-ary, not just in/out
    (spec.md 3.6). in_class/not_in_class/anti_class are each their own class
    label; the relation value itself IS the label, compared for equality,
    not reduced to a boolean."""
    assigned = {}
    violations = []
    universe = set()

    for e in events:
        entity = e["subject_id"]
        universe.add(entity)
        label = e["relation"]
        if entity in assigned and assigned[entity]["label"] != label:
            violations.append(
                {"entity": entity,
                 "conflicting_events": [assigned[entity]["event_id"], e["event_id"]]}
            )
        else:
            assigned[entity] = {"label": label, "event_id": e["event_id"]}

    classification = "inconsistent" if violations else "equivalence"
    return {"classification": classification, "universe": sorted(universe),
            "violations": violations}


def classify_group(events: list[dict]) -> dict:
    """A single relation cannot be both symmetric (equivalence) and antisymmetric
    (strict order) except in the empty/degenerate case -- proof: if aRb -> bRa
    (symmetric) and aRb & bRa -> a=b (antisymmetric), then aRb -> a=b for every
    pair, so no two distinct entities can be related at all. So when a bucket
    has BOTH order-type and equivalence-type events, that is not noise to
    resolve by majority vote -- it IS the finding: this speaker doesn't apply
    one coherent relation to this concept+form. Surfacing that (not silently
    picking the majority and discarding the rest) is one of the project's
    actual goals (spec.md 3.6)."""
    comparative = [e for e in events if e["relation"] in ORDER_RELATIONS]
    assignment = [e for e in events if e["relation"] in EQUIVALENCE_RELATIONS]

    if not comparative and not assignment:
        return {"classification": "no_discourse", "universe": [], "violations": []}
    if comparative and assignment:
        universe = sorted({e["subject_id"] for e in events} |
                           {e["object_id"] for e in events if e["object_id"]})
        return {
            "classification": "mixed_relation_types", "universe": universe,
            "violations": [],
            "comparative_events": [e["event_id"] for e in comparative],
            "assignment_events": [e["event_id"] for e in assignment],
        }
    if comparative:
        return classify_order(comparative)
    return classify_equivalence(assignment)


def classify_all(conn: sqlite3.Connection) -> list[dict]:
    results = []
    for (person_id, concept, form), events in fetch_event_groups(conn).items():
        result = classify_group(events)
        result.update({"person_id": person_id, "concept": concept, "form": form})
        results.append(result)
    return results


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    for r in sorted(classify_all(conn), key=lambda r: (r["concept"], r["person_id"])):
        print(f"speaker={r['person_id']} concept={r['concept']!r} form={r['form']}: "
              f"{r['classification']}  universe={r['universe']}  "
              f"violations={len(r['violations'])}")
    conn.close()


if __name__ == "__main__":
    main()

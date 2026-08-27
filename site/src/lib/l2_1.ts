// Client-side port of pipeline/classify/l2_1.py -- same logic, same taxonomy.
// Runs in the browser so a user's own comparisons can be classified live,
// with no backend (spec.md 3.2, "עדשה נגזרת ממשתמש").

export type Relation = "gt" | "eq_ordinal" | "in_class" | "not_in_class" | "anti_class";

export interface Event {
  relation: Relation;
  subject_id: string;
  object_id: string | null;
  event_id: string;
}

export interface ClassifyResult {
  classification: string;
  universe: string[];
  violations: unknown[];
}

const ORDER_RELATIONS = new Set<Relation>(["gt", "eq_ordinal"]);
const EQUIVALENCE_RELATIONS = new Set<Relation>(["in_class", "not_in_class", "anti_class"]);

function pairKey(a: string, b: string): string {
  return [a, b].sort().join("::");
}

export function classifyOrder(events: Event[]): ClassifyResult {
  const forwardEdges = new Set<string>(); // "a->b"
  const ties = new Set<string>();
  const violations: { pair: [string, string]; conflicting_event: string }[] = [];
  const universe = new Set<string>();

  for (const e of events) {
    universe.add(e.subject_id);
    if (e.object_id) universe.add(e.object_id);
  }

  for (const e of events) {
    const a = e.subject_id;
    const b = e.object_id as string;
    if (e.relation === "eq_ordinal") {
      ties.add(pairKey(a, b));
      continue;
    }
    if (forwardEdges.has(`${b}->${a}`)) {
      violations.push({ pair: [a, b], conflicting_event: e.event_id });
      continue;
    }
    forwardEdges.add(`${a}->${b}`);
  }

  let classification: string;
  if (violations.length > 0) {
    classification = "inconsistent";
  } else {
    const n = universe.size;
    const maxPairs = (n * (n - 1)) / 2;
    const comparedPairs = new Set<string>(ties);
    for (const edge of forwardEdges) {
      const [a, b] = edge.split("->");
      comparedPairs.add(pairKey(a, b));
    }
    if (ties.size > 0) {
      classification = "weak_order";
    } else if (comparedPairs.size >= maxPairs) {
      classification = "strict_order_total";
    } else {
      classification = "strict_order_partial";
    }
  }

  return { classification, universe: [...universe].sort(), violations };
}

export function classifyEquivalence(events: Event[]): ClassifyResult {
  // Each relation value IS its own class label (in_class/not_in_class/anti_class) --
  // compared for equality, not reduced to a boolean. Keeps "not X" and "anti X"
  // distinct classes, matching pipeline/classify/l2_1.py.
  const assigned = new Map<string, { label: Relation; event_id: string }>();
  const violations: { entity: string; conflicting_events: [string, string] }[] = [];
  const universe = new Set<string>();

  for (const e of events) {
    const entity = e.subject_id;
    universe.add(entity);
    const label = e.relation;
    const existing = assigned.get(entity);
    if (existing && existing.label !== label) {
      violations.push({ entity, conflicting_events: [existing.event_id, e.event_id] });
    } else {
      assigned.set(entity, { label, event_id: e.event_id });
    }
  }

  return {
    classification: violations.length > 0 ? "inconsistent" : "equivalence",
    universe: [...universe].sort(),
    violations,
  };
}

export function classifyGroup(events: Event[]): ClassifyResult {
  // A single relation can't be both symmetric (equivalence) and antisymmetric
  // (strict order) except in the degenerate/empty case -- so a bucket with
  // BOTH relation types present is the finding itself, not noise to resolve
  // by majority vote. Matches pipeline/classify/l2_1.py::classify_group.
  const comparative = events.filter((e) => ORDER_RELATIONS.has(e.relation));
  const assignment = events.filter((e) => EQUIVALENCE_RELATIONS.has(e.relation));

  if (comparative.length === 0 && assignment.length === 0) {
    return { classification: "no_discourse", universe: [], violations: [] };
  }
  if (comparative.length > 0 && assignment.length > 0) {
    const universe = new Set<string>();
    for (const e of events) {
      universe.add(e.subject_id);
      if (e.object_id) universe.add(e.object_id);
    }
    return { classification: "mixed_relation_types", universe: [...universe].sort(), violations: [] };
  }
  return comparative.length > 0
    ? classifyOrder(comparative)
    : classifyEquivalence(assignment);
}

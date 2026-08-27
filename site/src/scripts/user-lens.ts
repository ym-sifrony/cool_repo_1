// Client-side elicitation for ONE concept (this page is a per-concept route,
// spec.md 3.2 "עדשה נגזרת ממשתמש"). Kept single-concept on purpose -- combining
// every tracked concept into one giant questionnaire gets overwhelming as more
// concepts accumulate real data; each concept gets its own small flow instead,
// reached from that concept's own page.
//
// Page 1: one primary question per real pair for this concept, all shown at
// once, never filtered/reordered by other answers (they're independent probes;
// making them adaptive would anchor/lead the user). Page 2: follow-ups, which
// ARE adaptive -- they only make sense in light of a specific prior answer.
//
// Question design stays statement-based throughout (never "do you think X is
// a scale?"): every option is a concrete claim; picking one leaves a
// mechanical trace of structure without self-reporting it directly.
import { classifyEquivalence, classifyGroup, classifyOrder, type Event as L2Event, type Relation } from "../lib/l2_1";

interface Claim {
  id: string;
  speaker: string;
}
interface RawEvent {
  id: string;
  claim_id: string;
  relation: Relation;
  subject: string;
  object: string | null;
}
interface ConceptData {
  concept: string;
  claims: Claim[];
  events: RawEvent[];
}

interface PairQuestion {
  a: string;
  b: string;
}

type MainAnswer = "a_gt_b" | "b_gt_a" | "a_in_b_out" | "b_in_a_out" | "both_in" | "both_out" | "skip";
type FollowupAnswer = "no_scale" | "scale_top" | "scale_not_top" | "unsure";

const data: ConceptData = JSON.parse(document.getElementById("lens-data")!.textContent || "{}");
const concept = data.concept;

// Deliberately no persistence (no localStorage, no cookies, nothing sent
// anywhere): the result lives only in this page's in-memory JS state and is
// gone on navigation/reload. Avoids even the theoretical consent/legal
// question, and there's no feature today that actually needs it back.

const claimSpeaker = new Map(data.claims.map((c) => [c.id, c.speaker]));
const eventsWithSpeaker = data.events.map((e) => ({ ...e, speaker: claimSpeaker.get(e.claim_id) ?? "?" }));

const primaryQuestions: PairQuestion[] = [];
const seenPairs = new Set<string>();
for (const e of data.events) {
  if ((e.relation === "gt" || e.relation === "eq_ordinal") && e.object) {
    const key = [e.subject, e.object].sort().join("::");
    if (!seenPairs.has(key)) {
      seenPairs.add(key);
      primaryQuestions.push({ a: e.subject, b: e.object });
    }
  }
}

const primaryAnswers = new Map<number, MainAnswer>();
const followupAnswers = new Map<number, FollowupAnswer>();

function statementOptions(q: PairQuestion): [string, MainAnswer][] {
  return [
    [`${q.a} ${concept} יותר מ${q.b}`, "a_gt_b"],
    [`${q.a} ${concept} פחות מ${q.b}`, "b_gt_a"],
    [`${q.a} ${concept} ו${q.b} אינו ${concept}`, "a_in_b_out"],
    [`${q.b} ${concept} ו${q.a} אינו ${concept}`, "b_in_a_out"],
    [`גם ${q.a} וגם ${q.b} ${concept}ים`, "both_in"],
    [`גם ${q.a} וגם ${q.b} אינם ${concept}ים`, "both_out"],
    ["אינני יודע / אינני רוצה לענות", "skip"],
  ];
}

// only asymmetric-boolean answers get a tailored follow-up in this pass
function needsFollowup(main: MainAnswer): boolean {
  return main === "a_in_b_out" || main === "b_in_a_out";
}

function followupOptions(inEntity: string): [string, FollowupAnswer][] {
  return [
    [`${inEntity} ${concept} כמו כל שאר הפוליטיקאים ה${concept}ים -- אין "יותר" בתוך הקבוצה`, "no_scale"],
    [`${inEntity} הוא הכי ${concept} מכל הפוליטיקאים ה${concept}ים שיש`, "scale_top"],
    [`יש פוליטיקאים ${concept}ים יותר מ${inEntity}`, "scale_not_top"],
    ["אינני יודע / אין לי דעה מגובשת", "unsure"],
  ];
}

const page1El = document.getElementById("page1")!;
const page2El = document.getElementById("page2")!;
const resultEl = document.getElementById("result")!;
const nextBtn = document.getElementById("next-page")! as HTMLButtonElement;
const computeBtn = document.getElementById("compute")! as HTMLButtonElement;

function renderOptionGroup(container: HTMLElement, opts: [string, string][], onPick: (v: string) => void) {
  const group = document.createElement("div");
  for (const [label, value] of opts) {
    const btn = document.createElement("button");
    btn.className = "opt";
    btn.textContent = label;
    btn.addEventListener("click", () => {
      onPick(value);
      group.querySelectorAll("button.opt").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
    });
    group.appendChild(btn);
  }
  container.appendChild(group);
  return group;
}

// ---- page 1 ----
primaryQuestions.forEach((q, i) => {
  const div = document.createElement("div");
  div.className = "question";
  const p = document.createElement("p");
  p.textContent = `סמן את ההיגד שאתה הכי מסכים איתו, לגבי ${q.a} ו${q.b}:`;
  div.appendChild(p);
  renderOptionGroup(div, statementOptions(q), (v) => primaryAnswers.set(i, v as MainAnswer));
  page1El.appendChild(div);
});

if (primaryQuestions.length === 0) {
  page1El.innerHTML = '<p class="note">אין עדיין זוגות אמיתיים על המושג הזה כדי לשאול עליהם. נסה שוב אחרי שיצטברו עוד נתונים.</p>';
  nextBtn.disabled = true;
}

// ---- page 1 -> page 2 ----
nextBtn.addEventListener("click", () => {
  page1El.style.display = "none";
  nextBtn.style.display = "none";
  page2El.style.display = "block";

  const followupQuestions = primaryQuestions
    .map((q, i) => ({ q, i, main: primaryAnswers.get(i) }))
    .filter((x) => x.main && needsFollowup(x.main));

  if (followupQuestions.length === 0) {
    page2El.innerHTML = '<p class="note">אין שאלות המשך רלוונטיות לתשובות שנתת.</p>';
  }

  for (const { q, i, main } of followupQuestions) {
    const inEntity = main === "a_in_b_out" ? q.a : q.b;
    const div = document.createElement("div");
    div.className = "question";
    const p = document.createElement("p");
    p.textContent = `בהמשך לתשובתך על ${q.a}/${q.b}:`;
    div.appendChild(p);
    renderOptionGroup(div, followupOptions(inEntity), (v) => followupAnswers.set(i, v as FollowupAnswer));
    page2El.appendChild(div);
  }

  computeBtn.style.display = "inline-block";
});

// ---- compute ----
computeBtn.addEventListener("click", () => {
  const userEvents: L2Event[] = [];
  const scaleNotes: string[] = [];

  primaryQuestions.forEach((q, i) => {
    const main = primaryAnswers.get(i);
    if (!main || main === "skip") return;
    const id = (n: string) => `user_${i}_${n}`;

    switch (main) {
      case "a_gt_b":
        userEvents.push({ relation: "gt", subject_id: q.a, object_id: q.b, event_id: id("gt") });
        break;
      case "b_gt_a":
        userEvents.push({ relation: "gt", subject_id: q.b, object_id: q.a, event_id: id("gt") });
        break;
      case "both_in":
        userEvents.push({ relation: "in_class", subject_id: q.a, object_id: null, event_id: id("a") });
        userEvents.push({ relation: "in_class", subject_id: q.b, object_id: null, event_id: id("b") });
        break;
      case "both_out":
        userEvents.push({ relation: "not_in_class", subject_id: q.a, object_id: null, event_id: id("a") });
        userEvents.push({ relation: "not_in_class", subject_id: q.b, object_id: null, event_id: id("b") });
        break;
      case "a_in_b_out":
      case "b_in_a_out": {
        const inEntity = main === "a_in_b_out" ? q.a : q.b;
        const outEntity = main === "a_in_b_out" ? q.b : q.a;
        userEvents.push({ relation: "in_class", subject_id: inEntity, object_id: null, event_id: id("in") });
        userEvents.push({ relation: "not_in_class", subject_id: outEntity, object_id: null, event_id: id("out") });
        const fu = followupAnswers.get(i);
        if (fu === "scale_top" || fu === "scale_not_top") {
          scaleNotes.push(
            `דירוג פנימי דווח בתוך הקטגוריה: ${inEntity} ${
              fu === "scale_top" ? "מדווח כהכי" : "מדווח כ**לא** הכי"
            } ${concept} (מבנה noun+דירוג פנימי, לא סתירה)`
          );
        }
        break;
      }
    }
  });

  const result = classifyGroup(userEvents);

  const speakerNames = [...new Set(eventsWithSpeaker.map((e) => e.speaker))];
  const crossChecks = speakerNames.map((speaker) => {
    const speakerEvents: L2Event[] = eventsWithSpeaker
      .filter((e) => e.speaker === speaker)
      .map((e) => ({ relation: e.relation, subject_id: e.subject, object_id: e.object, event_id: e.id }));
    const merged = [...userEvents, ...speakerEvents];
    const mergedComparative = merged.filter((e) => e.relation === "gt" || e.relation === "eq_ordinal");
    const mergedAssignment = merged.filter((e) => e.relation === "in_class" || e.relation === "not_in_class");
    const orderCheck = mergedComparative.length ? classifyOrder(mergedComparative) : null;
    const eqCheck = mergedAssignment.length ? classifyEquivalence(mergedAssignment) : null;
    const conflict = (orderCheck?.violations.length ?? 0) + (eqCheck?.violations.length ?? 0) > 0;
    const overlap = speakerEvents.some(
      (se) =>
        userEvents.some((ue) => ue.subject_id === se.subject_id) ||
        userEvents.some((ue) => ue.object_id === se.subject_id)
    );
    return { speaker, conflict, overlap };
  });

  resultEl.style.display = "block";
  resultEl.innerHTML = `
    <p><strong>הסיווג שלך:</strong> ${result.classification} (יקום: ${result.universe.join(", ") || "—"})</p>
    ${scaleNotes.length ? `<p class="note">${scaleNotes.join("<br/>")}</p>` : ""}
    <table>
      <thead><tr><th>דובר</th><th>יחס למבנה שלך</th></tr></thead>
      <tbody>
        ${crossChecks
          .map(
            (c) =>
              `<tr><td>${c.speaker}</td><td>${
                !c.overlap ? "אין חפיפה בישויות" : c.conflict ? "סתירה ישירה על אותו זוג" : "אין סתירה ישירה"
              }</td></tr>`
          )
          .join("")}
      </tbody>
    </table>
    <p class="note">התוצאה הזו לא נשמרת ולא נשלחת לשום מקום — ברגע שתעזוב את העמוד, היא נעלמת.</p>
  `;
});

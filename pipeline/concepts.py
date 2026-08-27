"""Canonical concept list (spec.md, "רשימת המושגים ל-MVP והרחבה"). The single
source of truth every extraction script should search against -- NOT derived
from `SELECT DISTINCT concept FROM claims`, which only ever finds concepts
that already have an example claim and can therefore never discover the
FIRST claim for a newly-added concept (a real bug: for months the extractor
searched only the 3 words that happened to already be seeded, silently
ignoring the other ~20 already-approved concepts).

Keep this in sync with spec.md by hand when the concept table changes --
rejected concepts (חוקי, מוצדק) and the scope-limited one (יהודי, "כזהות
מדינה" only, not religious identity -- the distinction needs a human during
review, not a regex) are deliberately not filtered out here; the mechanical
layer's job is to find candidates, not to pre-judge admissibility.
"""

CONCEPTS = [
    # חזקים, מאומתים בדוגמה (גולן/גנץ/מירב כהן)
    "ציוני", "דתי", "ישראלי", "מוסרי",
    # חזקים, סבירים
    "חופשי", "דמוקרטי", "לגיטימי", "נאמן", "ממלכתי", "אידיאולוגי", "מתון",
    "קיצוני", "ימני", "שמאלי", "ליברלי", "פרוגרסיבי", "צודק", "מסורתי",
    "ישר", "נורמלי", "אמיתי",
    # תלויי הרפורמה המשפטית
    "שפיט", "חוקתי",
    # ממתינים לבדיקה אמפירית
    "יהודי",
]

// How many scenes a brief says it wants.
//
// Job bb6c6f1f: the brief opened "A 40-second drama in exactly 4 scenes" and
// the film had three -- the scene slider lives under "Advanced", defaults to 3,
// and the server clamps the script to whatever the slider said. The argument
// scene was folded into the first and its two lines of dialogue were lost.
// The brief is binding, so the form reads the number off the brief itself.

const WORDS = { two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8 };
const WORD_RE = Object.keys(WORDS).join("|");

// "4 scenes", "exactly four scenes", "4 sahne", "4-scene". Nothing else:
// "Scene 4 (resolution)" in a shot list is a label, not a count.
const PATTERNS = [
  new RegExp(`\\b(\\d{1,2})[\\s-]+(?:scenes?|sahne\\w*)\\b`, "i"),
  new RegExp(`\\b(${WORD_RE})[\\s-]+scenes?\\b`, "i"),
];

export function scenesAskedFor(brief, max = 8) {
  const text = String(brief || "");
  for (const re of PATTERNS) {
    const m = text.match(re);
    if (!m) continue;
    const n = /^\d+$/.test(m[1]) ? Number(m[1]) : WORDS[m[1].toLowerCase()];
    if (n >= 2 && n <= max) return n;
  }
  return null;
}

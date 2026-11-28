/**
 * The home page's FAQ, in display order — read by the rendered accordion
 * (HomeContent), the FAQPage JSON-LD (app/[locale]/page.js) and the Markdown
 * edition (lib/content/pages.js).
 *
 * One list for all three because Google drops an FAQ rich result whose markup
 * names a question the page does not show, and three hand-kept copies of
 * `[1, 2, 3, 4]` are how that happens the first time someone adds a fifth.
 *
 * WHY 5, 6 AND 7 COME FIRST. Questions 1-4 are about using the product once
 * you have chosen it — photo upload, demo mode, scene limits, ownership.
 * Nobody arrives at the site asking those. The questions an assistant is
 * actually asked are "what is MuseForge", "how does it keep characters
 * consistent" and "can it do a series", and an answer engine lifts the first
 * self-contained answer under a matching question. Those three now lead, each
 * answerable in two sentences that stand on their own when quoted.
 */
export const HOME_FAQ_KEYS = [5, 6, 7, 1, 2, 3, 4];

/**
 * The plan ladder, as the rest of the site quotes it.
 *
 * It lived inside app/[locale]/pricing/page.js, where exactly one thing read
 * it: that page's JSON-LD. It is now read by two — the JSON-LD and the Markdown
 * edition at /md/<locale>/pricing — and a constant with two readers belongs in
 * neither of them.
 *
 * This is still a MIRROR of the plan table in PricingContent.js, which builds
 * its cards from client-side translations and cannot be imported here. The two
 * are kept honest by `test_pricing_coherence.py`, which reads both files and
 * checks every figure against what stripe_integration actually grants and
 * charges. Moving this module means updating the path in that test, not
 * dropping the check.
 */

/* Mirrors the plan table in PricingContent. Kept in sync manually — the
   component builds its plans from client-side translations. */
/* The page leads with annual, so the structured data does too: `price` is the
   annual monthly-equivalent (10% off) that a rich result would show, and the
   monthly rate rides along as a second Offer rather than being the headline. */
export const PLAN_OFFERS = [
  { name: "Free", price: "0", desc: "Demo mode with placeholder assets — no API key required.", period: null },
  { name: "Creator (annual)", price: "53", desc: "16 credits per month for creators and educators, billed yearly.", period: "P1Y" },
  { name: "Creator (monthly)", price: "59", desc: "16 credits per month for creators and educators.", period: "P1M" },
  { name: "Pro (annual)", price: "116", desc: "36 credits per month for agencies and corporate teams, billed yearly.", period: "P1Y" },
  { name: "Pro (monthly)", price: "129", desc: "36 credits per month for agencies and corporate teams.", period: "P1M" },
];

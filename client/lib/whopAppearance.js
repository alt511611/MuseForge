/**
 * How Whop's embedded checkout is dressed so it reads as MuseForge, not as a
 * form from somewhere else.
 *
 * The form lives in Whop's own iframe: page CSS cannot reach it, so everything
 * here goes through `appearance` (docs.whop.com/elements/latest/appearance).
 * Values are literal hex because the frame has no access to our CSS variables;
 * they mirror the tokens in globals.css (--mf-bg, --mf-panel-2, --mf-line-strong,
 * --mf-ink*, --mf-violet*) and must be updated together with them.
 *
 * Whop validates each declaration and silently drops the ones it does not
 * allow, so a property that "does nothing" here is a property it refused.
 */

const BG = "#0a0a0f"; //          --mf-bg
const PANEL = "#101018"; //       --mf-panel
const PANEL_2 = "#16161f"; //     --mf-panel-2
const LINE = "#1e1e2b"; //        --mf-line
const LINE_STRONG = "#2a2a3d"; // --mf-line-strong
const INK = "#f1f3f8"; //         --mf-ink
const INK_2 = "#a8b0c2"; //       --mf-ink-2
const INK_3 = "#6b7488"; //       --mf-ink-3
const VIOLET = "#8b5cf6"; //      --mf-violet
const VIOLET_DEEP = "#6d28d9"; // --mf-violet-deep
const VIOLET_SOFT = "#b9a5fb"; // --mf-violet-soft
const ERR = "#f87171"; //         --mf-err

const field = {
  backgroundColor: BG,
  border: `1px solid ${LINE_STRONG}`,
  borderRadius: "10px",
  color: INK,
};

export const whopAppearance = {
  theme: {
    appearance: "dark",
    accentColor: "violet",
    grayColor: "slate",
    dangerColor: "red",
  },
  variables: { "--radius": "12px" },
  classes: {
    "whop-Checkout": { backgroundColor: BG, color: INK },
    "whop-CheckoutCollection": { backgroundColor: BG },
    "whop-CheckoutSummary": { backgroundColor: BG },
    "whop-CheckoutLayout": { backgroundColor: BG },
    "whop-CheckoutSeller": { color: INK_2 },
    "whop-CheckoutTotal": { color: INK, fontWeight: "700" },
    "whop-CheckoutPriceContext": { color: INK_3 },
    "whop-CheckoutDetailRow": { color: INK_2 },

    "whop-EmailLabel": { color: INK_2 },
    "whop-CardLabel": { color: INK_2 },
    "whop-AddressFieldLabel": { color: INK_2 },
    "whop-PaymentFieldLabel": { color: INK_2 },

    "whop-EmailInput": field,
    "whop-CardFieldInput": field,
    "whop-AddressFieldInput": field,
    "whop-AddressFieldSelect": field,
    "whop-PaymentFieldInput": field,
    "whop-CheckoutPromoInput": field,
    "whop-CardFieldInputFocused": { borderColor: VIOLET },
    "whop-CardFieldInputInvalid": { borderColor: ERR },

    "whop-PaymentMethodRow": {
      backgroundColor: PANEL_2,
      border: `1px solid ${LINE_STRONG}`,
      borderRadius: "12px",
      color: INK,
    },
    "whop-PaymentMethodRowSelected": { borderColor: VIOLET },
    "whop-PaymentMethodDetail": { backgroundColor: PANEL, borderColor: LINE },
    "whop-PaymentMethodTile": {
      backgroundColor: PANEL_2,
      border: `1px solid ${LINE_STRONG}`,
      borderRadius: "12px",
    },
    "whop-PaymentMethodTileSelected": { borderColor: VIOLET },

    "whop-CheckoutPayButton": {
      backgroundColor: VIOLET,
      backgroundImage: `linear-gradient(135deg, ${VIOLET}, ${VIOLET_DEEP})`,
      color: "#ffffff",
      opacity: "1",
      border: "none",
      borderRadius: "12px",
      fontWeight: "600",
      boxShadow: "0 0 24px rgba(139, 92, 246, 0.35)",
    },
    "whop-CheckoutTerms": { color: INK_3 },
    "whop-CheckoutPolicyLink": { color: VIOLET_SOFT },
    "whop-CheckoutError": { color: ERR },
  },
};

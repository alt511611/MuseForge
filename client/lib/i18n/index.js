import { LOCALES, LOCALE_CODES, DEFAULT_LOCALE } from "./locales";
import tA from "./t-a";
import tB from "./t-b";
import tC from "./t-c";
import tD from "./t-d";
import tExtra from "./t-extra";
import tPipeline from "./t-pipeline";

export { LOCALES, LOCALE_CODES, DEFAULT_LOCALE };

function mergeLocales(...parts) {
  const out = {};
  for (const part of parts) {
    for (const [loc, dict] of Object.entries(part)) {
      out[loc] = { ...(out[loc] || {}), ...dict };
    }
  }
  return out;
}

export const translations = mergeLocales(tA, tB, tC, tD, tExtra, tPipeline);

/**
 * Lookup a key in the given locale, falling back to English then the key itself.
 * @param {string} locale
 * @param {string} key
 * @param {Record<string, string|number>} [vars]
 * @returns {string}
 */
export function t(locale, key, vars) {
  const dict = translations[locale] ?? translations[DEFAULT_LOCALE] ?? {};
  let s = dict[key] ?? translations[DEFAULT_LOCALE]?.[key] ?? key;
  if (vars && typeof s === "string") {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replaceAll(`{${k}}`, String(v));
    }
  }
  return s;
}

import { LOCALES, LOCALE_CODES, DEFAULT_LOCALE } from "./locales";
import tA from "./t-a";
import tB from "./t-b";
import tC from "./t-c";
import tD from "./t-d";

export { LOCALES, LOCALE_CODES, DEFAULT_LOCALE };

export const translations = { ...tA, ...tB, ...tC, ...tD };

/**
 * Lookup a key in the given locale, falling back to English then the key itself.
 * @param {string} locale
 * @param {string} key
 * @returns {string}
 */
export function t(locale, key) {
  const dict = translations[locale] ?? translations[DEFAULT_LOCALE] ?? {};
  return dict[key] ?? translations[DEFAULT_LOCALE]?.[key] ?? key;
}

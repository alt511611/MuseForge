// Server-side translation lookup: page metadata, titles, descriptions.
//
// SERVER ONLY. It reaches every language through ./dictionary, so importing it
// from a "use client" module would pull all twenty into the browser bundle --
// which is the thing the per-locale split exists to stop. Client components get
// their strings from LanguageProvider's `t`, which reads the ONE dictionary the
// layout handed it.
//
// The `translations` object that used to live here is gone on purpose. It was
// the only thing a client import needed to touch to undo the split, and a
// convenience export that costs 95 KB the moment someone reaches for it is not
// a convenience.

import { LOCALES, LOCALE_CODES, DEFAULT_LOCALE } from "./locales";
import { getDictionary } from "./dictionary";

export { LOCALES, LOCALE_CODES, DEFAULT_LOCALE };

/** Cached per locale: generateMetadata calls this several times per page. */
const cache = new Map();

function dictionaryFor(locale) {
  const code = LOCALE_CODES.includes(locale) ? locale : DEFAULT_LOCALE;
  if (!cache.has(code)) cache.set(code, getDictionary(code));
  return cache.get(code);
}

/**
 * Lookup a key in the given locale, falling back to English then the key itself.
 * @param {string} locale
 * @param {string} key
 * @param {Record<string, string|number>} [vars]
 * @returns {string}
 */
export function t(locale, key, vars) {
  // The English fallback is already merged into the dictionary; a key that is
  // missing from both still returns itself, exactly as before.
  let s = dictionaryFor(locale)[key] ?? key;
  if (vars && typeof s === "string") {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replaceAll(`{${k}}`, String(v));
    }
  }
  return s;
}

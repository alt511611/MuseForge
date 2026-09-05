// One language's strings, assembled on the SERVER and handed to the client.
//
// WHY THIS FILE EXISTS. The dictionaries used to be merged at module scope and
// imported by LanguageContext, which is a client component -- so the browser
// bundle contained all twenty languages. Measured on a production build: a
// single 372 KB chunk (102 KB gzipped) on every page load, of which a reader
// used one twentieth. A visitor reading Turkish was downloading Thai.
//
// Nothing here reaches the browser as code. This module is imported only by
// the two root layouts, which are server components; what crosses to the
// client is the RETURN VALUE -- one language, serialised into the payload the
// page already sends. Importing it from a "use client" module would put all
// twenty back, so don't.
//
// The static map is deliberate. `await import(`./locales/${locale}.js`)` would
// read better and would make the set of languages invisible to the bundler,
// which then either bundles everything or nothing depending on its mood.

import ar from "./locales/ar";
import de from "./locales/de";
import en from "./locales/en";
import es from "./locales/es";
import fr from "./locales/fr";
import hi from "./locales/hi";
import id from "./locales/id";
import it from "./locales/it";
import ja from "./locales/ja";
import ko from "./locales/ko";
import nl from "./locales/nl";
import pl from "./locales/pl";
import pt from "./locales/pt";
import ro from "./locales/ro";
import ru from "./locales/ru";
import th from "./locales/th";
import tr from "./locales/tr";
import uk from "./locales/uk";
import vi from "./locales/vi";
import zh from "./locales/zh";

import { DEFAULT_LOCALE } from "./locales";

const DICTIONARIES = {
  ar, de, en, es, fr, hi, id, it, ja, ko,
  nl, pl, pt, ro, ru, th, tr, uk, vi, zh,
};

/**
 * Every string one locale needs, English filling the gaps.
 *
 * The fallback is merged HERE rather than left to the lookup, so the client
 * carries one flat object instead of two and never has to know that a second
 * dictionary exists. Behaviour is the same as the old runtime fallback chain
 * (locale -> English -> the key itself); only the place it happens moved.
 *
 * @param {string} locale
 * @returns {Record<string, string>}
 */
export function getDictionary(locale) {
  const base = DICTIONARIES[DEFAULT_LOCALE] || {};
  const active = DICTIONARIES[locale];
  return active && locale !== DEFAULT_LOCALE ? { ...base, ...active } : { ...base };
}

/** Whether a code has a dictionary at all (routing validates separately). */
export function hasDictionary(locale) {
  return Boolean(DICTIONARIES[locale]);
}

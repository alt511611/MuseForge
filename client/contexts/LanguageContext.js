"use client";

import { createContext, useContext, useCallback, useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";
// Metadata only (names, flags, direction) -- 20 short rows. The STRINGS
// arrive as a prop: importing them here is what used to put all twenty
// languages in every visitor's bundle. See lib/i18n/dictionary.js.
import { LOCALES, LOCALE_CODES, DEFAULT_LOCALE } from "../lib/i18n/locales";
import { splitLocale, withLocale } from "../lib/i18n/routing";

const LanguageContext = createContext(null);

/* Remembers the visitor's choice so the middleware-served default (`/`) can be
   nudged toward their language on a later visit. The URL, not this key, is the
   source of truth — it exists only to make the switcher sticky. */
const LS_KEY = "mf_locale";

/* A provider mounted without a dictionary still renders: t() answers with the
   key. Stable identity so it cannot re-trigger the memo on every render. */
const EMPTY_DICTIONARY = {};

/**
 * The active locale comes from the URL segment (app/[locale]), passed down by
 * the root layout. That makes it available during SSR, so translated markup is
 * in the initial HTML instead of appearing after hydration.
 *
 * `dictionary` is that locale's strings, already merged over English by the
 * layout (lib/i18n/dictionary.getDictionary). It is a prop rather than an
 * import because an import here is a client import: it would carry all twenty
 * languages into the browser bundle -- 372 KB of JS (102 KB gzipped) on every
 * page load, nineteen twentieths of it unread. Handing one language down keeps
 * SSR translated, which a lazily loaded dictionary would not.
 */
export function LanguageProvider({ children, locale: localeProp, dictionary }) {
  const locale = LOCALE_CODES.includes(localeProp) ? localeProp : DEFAULT_LOCALE;
  const dict = dictionary || EMPTY_DICTIONARY;
  const router = useRouter();
  const pathname = usePathname();

  /** Switching language is a navigation: /pricing -> /tr/pricing. */
  const setLocale = useCallback(
    (code) => {
      if (!LOCALE_CODES.includes(code) || code === locale) return;
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(LS_KEY, code);
        } catch {
          /* private mode / storage disabled — the URL still carries the locale */
        }
      }
      const { path } = splitLocale(pathname || "/");
      // Read the query straight off the URL: useSearchParams() would force a
      // Suspense boundary here and opt every page out of static rendering.
      const query = typeof window !== "undefined" ? window.location.search : "";
      router.push(withLocale(path, code) + query);
    },
    [locale, pathname, router]
  );

  const t = useCallback(
    (key, vars) => {
      // English is already merged in under the active locale, so a missing
      // key means missing everywhere -- and then the key itself is the
      // honest answer, exactly as it was before the split.
      let s = dict[key] ?? key;
      if (vars && typeof s === "string") {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replaceAll(`{${k}}`, String(v));
        }
      }
      return s;
    },
    [dict]
  );

  /** Prefix a site-relative href with the active locale. */
  const localeHref = useCallback((path) => withLocale(path, locale), [locale]);

  const value = useMemo(
    () => ({ locale, setLocale, t, localeHref, LOCALES, LOCALE_CODES }),
    [locale, setLocale, t, localeHref]
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used inside <LanguageProvider>");
  return ctx;
}

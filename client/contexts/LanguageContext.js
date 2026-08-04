"use client";

import { createContext, useContext, useCallback, useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LOCALES, LOCALE_CODES, DEFAULT_LOCALE, translations } from "../lib/i18n/index";
import { splitLocale, withLocale } from "../lib/i18n/routing";

const LanguageContext = createContext(null);

/* Remembers the visitor's choice so the middleware-served default (`/`) can be
   nudged toward their language on a later visit. The URL, not this key, is the
   source of truth — it exists only to make the switcher sticky. */
const LS_KEY = "mf_locale";

/**
 * The active locale comes from the URL segment (app/[locale]), passed down by
 * the root layout. That makes it available during SSR, so translated markup is
 * in the initial HTML instead of appearing after hydration.
 */
export function LanguageProvider({ children, locale: localeProp }) {
  const locale = LOCALE_CODES.includes(localeProp) ? localeProp : DEFAULT_LOCALE;
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
      const dict = translations[locale] ?? translations[DEFAULT_LOCALE] ?? {};
      let s = dict[key] ?? translations[DEFAULT_LOCALE]?.[key] ?? key;
      if (vars && typeof s === "string") {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replaceAll(`{${k}}`, String(v));
        }
      }
      return s;
    },
    [locale]
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

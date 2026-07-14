"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { LOCALES, LOCALE_CODES, DEFAULT_LOCALE, translations } from "../lib/i18n/index";

const LanguageContext = createContext(null);

const LS_KEY = "mf_locale";

function detectLocale() {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = localStorage.getItem(LS_KEY);
  if (stored && LOCALE_CODES.includes(stored)) return stored;
  // navigator.language e.g. "tr-TR" → "tr"
  const navLang = navigator.language?.split("-")[0]?.toLowerCase();
  if (navLang && LOCALE_CODES.includes(navLang)) return navLang;
  return DEFAULT_LOCALE;
}

export function LanguageProvider({ children }) {
  const [locale, setLocaleState] = useState(DEFAULT_LOCALE);

  useEffect(() => {
    setLocaleState(detectLocale());
  }, []);

  // Sync html[lang] and html[dir] on locale change
  useEffect(() => {
    if (typeof document === "undefined") return;
    const meta = LOCALES[locale] ?? LOCALES[DEFAULT_LOCALE];
    document.documentElement.lang = locale;
    document.documentElement.dir = meta.dir;
  }, [locale]);

  const setLocale = useCallback((code) => {
    if (!LOCALE_CODES.includes(code)) return;
    setLocaleState(code);
    if (typeof window !== "undefined") localStorage.setItem(LS_KEY, code);
  }, []);

  const t = useCallback(
    (key) => {
      const dict = translations[locale] ?? translations[DEFAULT_LOCALE] ?? {};
      return dict[key] ?? translations[DEFAULT_LOCALE]?.[key] ?? key;
    },
    [locale]
  );

  return (
    <LanguageContext.Provider value={{ locale, setLocale, t, LOCALES, LOCALE_CODES }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used inside <LanguageProvider>");
  return ctx;
}

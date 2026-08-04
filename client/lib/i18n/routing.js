import { LOCALE_CODES, DEFAULT_LOCALE, LOCALES } from "./locales";

/**
 * URL strategy: "as-needed" prefixing.
 *
 *   English  -> /pricing            (no prefix, so existing indexed URLs and
 *                                    their link equity are untouched)
 *   Others   -> /tr/pricing, /ja/pricing, ...
 *
 * middleware.js rewrites the unprefixed form to /en/... internally, so every
 * route still resolves through app/[locale]/ and there is exactly one root
 * layout. The address bar keeps the clean English URL.
 */

export { LOCALE_CODES, DEFAULT_LOCALE, LOCALES };

/** Paths that are never localized — auth callbacks, API proxy, assets. */
export const UNLOCALIZED_PREFIXES = ["/auth", "/api", "/_next"];

export function isLocale(value) {
  return LOCALE_CODES.includes(value);
}

/** "" for English, "/tr" for everything else. */
export function localePrefix(locale) {
  return !locale || locale === DEFAULT_LOCALE ? "" : `/${locale}`;
}

/**
 * Prefix a site-relative path for the given locale.
 * Query strings and hashes are preserved.
 *   withLocale("/pricing", "tr")  -> "/tr/pricing"
 *   withLocale("/pricing", "en")  -> "/pricing"
 *   withLocale("/", "tr")         -> "/tr"
 */
export function withLocale(path, locale) {
  if (typeof path !== "string" || !path.startsWith("/")) return path;
  if (UNLOCALIZED_PREFIXES.some((p) => path === p || path.startsWith(p + "/"))) {
    return path;
  }
  const prefix = localePrefix(locale);
  if (!prefix) return path;
  return path === "/" ? prefix : `${prefix}${path}`;
}

/**
 * Split a pathname into its locale and the unprefixed remainder.
 *   splitLocale("/tr/pricing") -> { locale: "tr", path: "/pricing" }
 *   splitLocale("/pricing")    -> { locale: "en", path: "/pricing" }
 */
export function splitLocale(pathname) {
  const [, first, ...rest] = pathname.split("/");
  if (isLocale(first)) {
    const path = "/" + rest.join("/");
    return { locale: first, path: path === "/" ? "/" : path.replace(/\/$/, "") };
  }
  return { locale: DEFAULT_LOCALE, path: pathname };
}

/** BCP-47 tag for <html lang> and og:locale. Same as the code for our set. */
export function htmlLang(locale) {
  return isLocale(locale) ? locale : DEFAULT_LOCALE;
}

export function textDirection(locale) {
  return LOCALES[locale]?.dir ?? "ltr";
}

/* og:locale wants language_TERRITORY. Facebook's parser rejects a bare
   language code, so each locale gets its most common territory. */
const OG_TERRITORY = {
  en: "US", tr: "TR", es: "ES", fr: "FR", de: "DE", pt: "BR", it: "IT",
  ru: "RU", ar: "SA", hi: "IN", ja: "JP", ko: "KR", zh: "CN", id: "ID",
  vi: "VN", th: "TH", pl: "PL", nl: "NL", uk: "UA", ro: "RO",
};

export function ogLocale(locale) {
  const code = isLocale(locale) ? locale : DEFAULT_LOCALE;
  return `${code}_${OG_TERRITORY[code] ?? code.toUpperCase()}`;
}

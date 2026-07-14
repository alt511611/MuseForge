// Supported locales metadata.  dir: "rtl" only for Arabic.
export const LOCALES = {
  en: { name: "English",            nativeName: "English",            flag: "🇬🇧", dir: "ltr" },
  tr: { name: "Turkish",            nativeName: "Türkçe",             flag: "🇹🇷", dir: "ltr" },
  es: { name: "Spanish",            nativeName: "Español",            flag: "🇪🇸", dir: "ltr" },
  fr: { name: "French",             nativeName: "Français",           flag: "🇫🇷", dir: "ltr" },
  de: { name: "German",             nativeName: "Deutsch",            flag: "🇩🇪", dir: "ltr" },
  pt: { name: "Portuguese",         nativeName: "Português",          flag: "🇧🇷", dir: "ltr" },
  it: { name: "Italian",            nativeName: "Italiano",           flag: "🇮🇹", dir: "ltr" },
  ru: { name: "Russian",            nativeName: "Русский",            flag: "🇷🇺", dir: "ltr" },
  ar: { name: "Arabic",             nativeName: "العربية",            flag: "🇸🇦", dir: "rtl" },
  hi: { name: "Hindi",              nativeName: "हिन्दी",             flag: "🇮🇳", dir: "ltr" },
  ja: { name: "Japanese",           nativeName: "日本語",              flag: "🇯🇵", dir: "ltr" },
  ko: { name: "Korean",             nativeName: "한국어",              flag: "🇰🇷", dir: "ltr" },
  zh: { name: "Chinese",            nativeName: "中文",                flag: "🇨🇳", dir: "ltr" },
  id: { name: "Indonesian",         nativeName: "Bahasa Indonesia",   flag: "🇮🇩", dir: "ltr" },
  vi: { name: "Vietnamese",         nativeName: "Tiếng Việt",         flag: "🇻🇳", dir: "ltr" },
  th: { name: "Thai",               nativeName: "ภาษาไทย",            flag: "🇹🇭", dir: "ltr" },
  pl: { name: "Polish",             nativeName: "Polski",             flag: "🇵🇱", dir: "ltr" },
  nl: { name: "Dutch",              nativeName: "Nederlands",         flag: "🇳🇱", dir: "ltr" },
  uk: { name: "Ukrainian",          nativeName: "Українська",         flag: "🇺🇦", dir: "ltr" },
  ro: { name: "Romanian",           nativeName: "Română",             flag: "🇷🇴", dir: "ltr" },
};

export const LOCALE_CODES = Object.keys(LOCALES);
export const DEFAULT_LOCALE = "en";

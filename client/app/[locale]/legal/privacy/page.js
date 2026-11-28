import PrivacyContent from "./PrivacyContent";
import { canonical } from "../../../../lib/seo";
import { isLocale, DEFAULT_LOCALE } from "../../../../lib/i18n/routing";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: "Privacy Policy",
    description:
      "How MuseForge collects, uses, and protects your data — accounts, generated videos, payments, and cookies.",
    /* The body is English at every prefix — only the chrome is translated —
       so only English is the edition. Twenty self-canonical copies were
       twenty "Duplicate title" findings in OpenSEO's 2026-10-08 crawl, the
       same defect /solutions/* had; see canonical(). */
    alternates: canonical("/legal/privacy", locale, [DEFAULT_LOCALE]),
  };
}

export default function PrivacyPage() {
  return <PrivacyContent />;
}

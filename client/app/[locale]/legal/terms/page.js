import TermsContent from "./TermsContent";
import { canonical } from "../../../../lib/seo";
import { isLocale, DEFAULT_LOCALE } from "../../../../lib/i18n/routing";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: "Terms of Service",
    description:
      "The terms governing your use of MuseForge — plans, credits, content ownership, and acceptable use.",
    /* The body is English at every prefix — only the chrome is translated —
       so only English is the edition. Twenty self-canonical copies were
       twenty "Duplicate title" findings in OpenSEO's 2026-10-08 crawl, the
       same defect /solutions/* had; see canonical(). */
    alternates: canonical("/legal/terms", locale, [DEFAULT_LOCALE]),
  };
}

export default function TermsPage() {
  return <TermsContent />;
}

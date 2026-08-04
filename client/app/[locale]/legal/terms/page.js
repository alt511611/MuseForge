import TermsContent from "./TermsContent";
import { canonical } from "../../../../lib/seo";
import { isLocale } from "../../../../lib/i18n/routing";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: "Terms of Service",
    description:
      "The terms governing your use of MuseForge — plans, credits, content ownership, and acceptable use.",
    alternates: canonical("/legal/terms", locale),
  };
}

export default function TermsPage() {
  return <TermsContent />;
}

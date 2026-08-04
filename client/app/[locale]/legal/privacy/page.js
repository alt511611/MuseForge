import PrivacyContent from "./PrivacyContent";
import { canonical } from "../../../../lib/seo";
import { isLocale } from "../../../../lib/i18n/routing";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: "Privacy Policy",
    description:
      "How MuseForge collects, uses, and protects your data — accounts, generated videos, payments, and cookies.",
    alternates: canonical("/legal/privacy", locale),
  };
}

export default function PrivacyPage() {
  return <PrivacyContent />;
}

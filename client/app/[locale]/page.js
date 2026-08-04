import HomeContent from "./HomeContent";
import { t } from "../../lib/i18n/index";
import { isLocale } from "../../lib/i18n/routing";
import {
  JsonLd,
  canonical,
  openGraphFor,
  organizationSchema,
  websiteSchema,
  softwareApplicationSchema,
  faqSchema,
} from "../../lib/seo";

const FAQ_KEYS = [1, 2, 3, 4];

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  const title = `MuseForge — ${t(locale, "hero_sub")}`;
  const description = t(locale, "hero_desc");
  return {
    title,
    description,
    alternates: canonical("/", locale),
    openGraph: openGraphFor({ title, description, path: "/", locale }),
  };
}

export default function HomePage({ params: { locale } }) {
  /* The FAQ copy is translated, so every locale ships FAQPage markup that
     matches the text actually rendered on that URL. */
  const faq = FAQ_KEYS.map((n) => ({
    q: t(locale, `faq_${n}_q`),
    a: t(locale, `faq_${n}_a`),
  }));

  return (
    <>
      <JsonLd
        graph={[
          organizationSchema(),
          websiteSchema(locale),
          softwareApplicationSchema(locale),
          faqSchema(faq),
        ]}
      />
      <HomeContent />
    </>
  );
}

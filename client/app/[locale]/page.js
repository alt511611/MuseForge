import HomeContent from "./HomeContent";
import { t } from "../../lib/i18n/index";
import { isLocale, DEFAULT_LOCALE } from "../../lib/i18n/routing";
import { mdPath } from "../../lib/content/pages";
import {
  JsonLd,
  canonical,
  withMarkdown,
  openGraphFor,
  organizationSchema,
  websiteSchema,
  softwareApplicationSchema,
  faqSchema,
} from "../../lib/seo";
import { HOME_FAQ_KEYS as FAQ_KEYS } from "../../lib/faq";

/* English carries a search-tuned title, the way /pricing does; every other
   locale keeps its translated hero line, which is what that URL shows.

   WHY THESE WORDS. "Idea to Cinematic Video — Agentic AI Studio" names
   nothing anybody types. OpenSEO, US, 2026-10-08: "ai movie maker" 2,900
   searches a month at difficulty 24, "ai film maker" 2,900 at 35, "ai
   filmmaking" 2,900 at 8. The domain ranked for zero keywords on that date,
   so the title is the strongest on-page signal it has, and it was spent on a
   phrase only the product team uses. "Short film" stays because it is what the product
   actually delivers, and it is the head of "ai short film generator". */
const EN_TITLE = "AI Movie Maker — Turn One Idea into a Short Film | MuseForge";
const EN_DESCRIPTION =
  "MuseForge is an AI film maker: type one idea and AI agents write the script, storyboard every shot, keep characters consistent and cut a finished short film.";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  const english = locale === DEFAULT_LOCALE;
  const title = english
    ? { absolute: EN_TITLE }
    : `MuseForge — ${t(locale, "hero_sub")}`;
  const description = english ? EN_DESCRIPTION : t(locale, "hero_desc");
  const social = english ? EN_TITLE : title;
  return {
    title,
    description,
    alternates: withMarkdown(canonical("/", locale), mdPath("home", locale)),
    openGraph: openGraphFor({ title: social, description, path: "/", locale }),
    twitter: { title: social, description },
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

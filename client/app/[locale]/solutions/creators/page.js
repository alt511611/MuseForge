import SolutionPage from "../../../../components/SolutionPage";
import { Film, Sparkles, Users, Zap } from "lucide-react";
import Breadcrumbs from "../../../../components/Breadcrumbs";
import { JsonLd, canonical, breadcrumbSchema, openGraphFor } from "../../../../lib/seo";
import { t } from "../../../../lib/i18n/index";
import { isLocale, withLocale, DEFAULT_LOCALE } from "../../../../lib/i18n/routing";
import { CONTENT } from "./content";

/* The copy lives in ./content.js so the Markdown edition at
   /md/<locale>/solutions/creators renders the same words. Only the presentation —
   icons, the two-tone heading, the breadcrumb trail — is assembled here. */

const PATH = "/solutions/creators";

/* This page's content is English only (./content.js). Every other
   locale prefix still renders it -- so a Thai visitor gets Thai chrome
   around English copy -- but only English is the canonical, indexable
   edition; see the note in generateMetadata. */
const ONLY_LOCALE = [DEFAULT_LOCALE];

const trail = (locale) => [
  { name: t(locale, "nav_home"), path: withLocale("/", locale) },
  { name: t(locale, "sol_creators"), path: withLocale(PATH, locale) },
];

/* Icon elements cannot live in content.js: a route handler imports that module
   and renders no React. Names in, components out. */
const ICONS = { Film, Sparkles, Users, Zap };

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  /* CONTENT is English only (see ./content.js) -- ONLY_LOCALE tells canonical()
     and openGraphFor() that this page has no content of its own outside
     English, so a non-English URL canonicalizes to the English one instead of
     to itself. Twenty self-canonicalizing copies of one page is how
     "Duplicate without user-selected canonical" ends up in Search Console. */
  return {
    title: { absolute: `${CONTENT.title} | MuseForge` },
    description: CONTENT.description,
    alternates: canonical(PATH, locale, ONLY_LOCALE),
    openGraph: openGraphFor({
      title: CONTENT.title,
      description: CONTENT.description,
      path: PATH,
      locale,
      available: ONLY_LOCALE,
    }),
  };
}

export default function CreatorsPage({ params: { locale } }) {
  const TRAIL = trail(locale);
  const PageIcon = Users;

  return (
    <>
      <JsonLd graph={[breadcrumbSchema(TRAIL)]} />
      <SolutionPage
        breadcrumbs={<Breadcrumbs trail={TRAIL} />}
        icon={<PageIcon size={12} />}
        accentColor={CONTENT.accentColor}
        badge={CONTENT.badge}
        heading={
          <>
            <span className="gradient-text">{CONTENT.headingLead}</span>
            <br />
            <span style={{ color: "var(--mf-ink)" }}>{CONTENT.headingRest}</span>
          </>
        }
        subheading={CONTENT.subheading}
        segment="creators"
        useCases={CONTENT.useCases.map((u) => {
          const Icon = ICONS[u.icon];
          return {
            ...u,
            icon: <Icon size={20} style={{ color: CONTENT.accentColor }} />,
          };
        })}
        differentiators={CONTENT.differentiators}
        planCard={CONTENT.planCard}
        ctaBanner={CONTENT.ctaBanner}
      />
    </>
  );
}


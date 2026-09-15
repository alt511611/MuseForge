import SolutionPage from "../../../../components/SolutionPage";
import { Building2, Film, Globe, Megaphone } from "lucide-react";
import Breadcrumbs from "../../../../components/Breadcrumbs";
import { JsonLd, canonical, breadcrumbSchema, openGraphFor } from "../../../../lib/seo";
import { t } from "../../../../lib/i18n/index";
import { isLocale, withLocale } from "../../../../lib/i18n/routing";
import { CONTENT } from "./content";

/* The copy lives in ./content.js so the Markdown edition at
   /md/<locale>/solutions/agencies renders the same words. Only the presentation —
   icons, the two-tone heading, the breadcrumb trail — is assembled here. */

const PATH = "/solutions/agencies";

const trail = (locale) => [
  { name: t(locale, "nav_home"), path: withLocale("/", locale) },
  { name: t(locale, "sol_agencies"), path: withLocale(PATH, locale) },
];

/* Icon elements cannot live in content.js: a route handler imports that module
   and renders no React. Names in, components out. */
const ICONS = { Building2, Film, Globe, Megaphone };

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: { absolute: `${CONTENT.title} | MuseForge` },
    description: CONTENT.description,
    alternates: canonical(PATH, locale),
    openGraph: openGraphFor({
      title: CONTENT.title,
      description: CONTENT.description,
      path: PATH,
      locale,
    }),
  };
}

export default function AgenciesPage({ params: { locale } }) {
  const TRAIL = trail(locale);
  const PageIcon = Building2;

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
        segment="agencies"
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


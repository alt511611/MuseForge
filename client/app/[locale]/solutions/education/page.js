import SolutionPage from "../../../../components/SolutionPage";
import { BookOpen, GraduationCap, Lightbulb, Users } from "lucide-react";
import Breadcrumbs from "../../../../components/Breadcrumbs";
import { JsonLd, canonical, breadcrumbSchema, openGraphFor } from "../../../../lib/seo";
import { t } from "../../../../lib/i18n/index";
import { isLocale, withLocale } from "../../../../lib/i18n/routing";
import { CONTENT } from "./content";

/* The copy lives in ./content.js so the Markdown edition at
   /md/<locale>/solutions/education renders the same words. Only the presentation —
   icons, the two-tone heading, the breadcrumb trail — is assembled here. */

const PATH = "/solutions/education";

const trail = (locale) => [
  { name: t(locale, "nav_home"), path: withLocale("/", locale) },
  { name: t(locale, "sol_education"), path: withLocale(PATH, locale) },
];

/* Icon elements cannot live in content.js: a route handler imports that module
   and renders no React. Names in, components out. */
const ICONS = { BookOpen, GraduationCap, Lightbulb, Users };

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

export default function EducationPage({ params: { locale } }) {
  const TRAIL = trail(locale);
  const PageIcon = BookOpen;

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
        segment="education"
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


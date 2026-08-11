import SolutionPage from "../../../../components/SolutionPage";
import { Building2, Megaphone, Film, Globe } from "lucide-react";
import Breadcrumbs from "../../../../components/Breadcrumbs";
import { JsonLd, canonical, breadcrumbSchema, openGraphFor } from "../../../../lib/seo";
import { t } from "../../../../lib/i18n/index";
import { isLocale, withLocale } from "../../../../lib/i18n/routing";

const PATH = "/solutions/agencies";
const TITLE = "Corporate AI Video Studio for Ad Agencies";
const DESCRIPTION =
  "Generate product launch videos, corporate brand films, and campaign concepts with MuseForge's multi-agent AI pipeline.";

const trail = (locale) => [
  { name: t(locale, "nav_home"), path: withLocale("/", locale) },
  { name: t(locale, "sol_agencies"), path: withLocale(PATH, locale) },
];

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: { absolute: `${TITLE} | MuseForge` },
    description: DESCRIPTION,
    alternates: canonical(PATH, locale),
    openGraph: openGraphFor({ title: TITLE, description: DESCRIPTION, path: PATH, locale }),
  };
}

export default function AgenciesPage({ params: { locale } }) {
  const TRAIL = trail(locale);
  return (
    <>
    <JsonLd graph={[breadcrumbSchema(TRAIL)]} />
    <SolutionPage
      breadcrumbs={<Breadcrumbs trail={TRAIL} />}
      icon={<Building2 size={12} />}
      accentColor="var(--mf-violet)"
      badge="Ad Agencies & Corporate Comms"
      heading={<><span className="gradient-text">Pitch-Ready Video,</span><br /><span style={{ color: "var(--mf-ink)" }}>Generated in Minutes</span></>}
      subheading="From brand brief to cinematic storyboard — MuseForge's multi-agent pipeline handles scripting, visual design, and production so your team can focus on strategy."
      segment="agencies"
      useCases={[
        {
          icon: <Megaphone size={20} style={{ color: "var(--mf-violet)" }} />,
          title: "Product Launch Videos",
          desc: "Turn a product brief into a cinematic reveal — complete script, shot list, and assembled video ready for client review.",
          sample: "A luxury car emerges from desert dust at golden hour — slow cinematic preset, 16:9",
        },
        {
          icon: <Building2 size={20} style={{ color: "var(--mf-violet)" }} />,
          title: "Corporate Brand Films",
          desc: "Produce polished brand identity videos for pitches and investor decks without scheduling a full production crew.",
          sample: "Tech company headquarters montage — handheld kinetic preset, dynamic pacing",
        },
        {
          icon: <Film size={20} style={{ color: "var(--mf-violet)" }} />,
          title: "Campaign Concept Reels",
          desc: "Visualise multiple creative directions in parallel — present 3 concepts in the time it used to take to storyboard 1.",
          sample: "Seasonal campaign — warm color grade, character locked across all 5 scenes",
        },
        {
          icon: <Globe size={20} style={{ color: "var(--mf-violet)" }} />,
          title: "Multi-Market Localisation",
          desc: "Generate region-specific visual concepts with different cultural contexts — same brief, different executions.",
          sample: "Same product story adapted for 3 different visual markets",
        },
      ]}
      differentiators={[
        {
          title: "Character Consistency Lock",
          desc: "Upload a brand ambassador or actor photo once — MuseForge locks that face across every scene. No re-briefing visual artists.",
        },
        {
          title: "Cinema Studio Director Presets",
          desc: "Slow Cinematic, Noir Mystery, Dynamic Action — presets guide AI camera movement and color grade to match your brand tone instantly.",
        },
        {
          title: "Complete Pipeline in One Request",
          desc: "Screenwriter, storyboard artist, frame generator, and video assembler — all agents collaborate end-to-end. No handoffs between tools.",
        },
        {
          title: "36 Credits / Month on Pro",
          desc: "Run seven full five-scene video projects per month for a flat $129. Ideal for agencies running multiple concurrent campaigns.",
        },
      ]}
      planCard={{
        name: "Pro",
        price: "$129",
        period: "/ mo",
        credits: 36,
        highlight: true,
        cta: "Upgrade to Pro",
        ctaHref: "/pricing",
        features: ["36 credits/mo", "Up to 24 scenes (~3 min)", "All director presets", "HD export", "No watermark"],
      }}
      ctaBanner={{
        title: "Ready to Cut Production Time by 80%?",
        desc: "Try demo mode free — no API key, no credit card. See a full storyboard in under a minute.",
        btnText: "Try Demo Free",
        btnHref: "/",
      }}
    />
    </>
  );
}

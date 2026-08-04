import SolutionPage from "../../../../components/SolutionPage";
import { Users, Sparkles, Film, Zap } from "lucide-react";
import Breadcrumbs from "../../../../components/Breadcrumbs";
import { JsonLd, canonical, breadcrumbSchema, openGraphFor } from "../../../../lib/seo";
import { t } from "../../../../lib/i18n/index";
import { isLocale, withLocale } from "../../../../lib/i18n/routing";

const PATH = "/solutions/creators";
const TITLE = "AI Micro-Drama Studio for Content Creators";
const DESCRIPTION =
  "Build micro-drama series, social video stories, and cinematic content at scale with MuseForge's multi-agent AI pipeline.";

const trail = (locale) => [
  { name: t(locale, "nav_home"), path: withLocale("/", locale) },
  { name: t(locale, "sol_creators"), path: withLocale(PATH, locale) },
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

export default function CreatorsPage({ params: { locale } }) {
  const TRAIL = trail(locale);
  return (
    <>
    <JsonLd graph={[breadcrumbSchema(TRAIL)]} />
    <SolutionPage
      breadcrumbs={<Breadcrumbs trail={TRAIL} />}
      icon={<Users size={12} />}
      accentColor="var(--mf-violet-deep)"
      badge="Content Creators & Solo Filmmakers"
      heading={<><span className="gradient-text">Your Entire Studio,</span><br /><span style={{ color: "var(--mf-ink)" }}>In One Prompt</span></>}
      subheading="Write an idea. MuseForge builds the script, designs the storyboard, generates every frame, and stitches a cinematic video — all in a few minutes."
      useCases={[
        {
          icon: <Film size={20} style={{ color: "var(--mf-violet-deep)" }} />,
          title: "Micro-Drama Series",
          desc: "Ship a new episode every day. Each run produces a complete short film — consistent characters, coherent plot, cinematic look.",
          sample: "Episode 3: A detective discovers a hidden room — noir mystery preset, 9:16 vertical",
        },
        {
          icon: <Sparkles size={20} style={{ color: "var(--mf-violet-deep)" }} />,
          title: "Social Media Story Arcs",
          desc: "Turn a trending topic or personal story into a shareable cinematic reel optimised for Instagram, TikTok, or YouTube Shorts.",
          sample: "Inspirational athlete journey — dynamic action preset, 1:1 square format",
        },
        {
          icon: <Zap size={20} style={{ color: "var(--mf-violet-deep)" }} />,
          title: "Rapid Concept Prototyping",
          desc: "Test 10 story ideas in the time it used to take to shoot 1. Validate audience hooks before investing in real production.",
          sample: "3 different romantic drama opening scenes — compare audience response",
        },
        {
          icon: <Users size={20} style={{ color: "var(--mf-violet-deep)" }} />,
          title: "Consistent Characters Across Episodes",
          desc: "Upload a single reference photo and MuseForge maintains that character's appearance in every scene of every episode.",
          sample: "Recurring protagonist across 5-episode arc — character lock active",
        },
      ]}
      differentiators={[
        {
          title: "16 Credits / Month for $59",
          desc: "Enough for about three full 5-scene videos per month — roughly $20/video all-in on Creator.",
        },
        {
          title: "Demo Mode — Try Before You Spend",
          desc: "Generate a complete storyboard preview without spending a single credit. Perfect for idea validation before committing.",
        },
        {
          title: "Multiple Aspect Ratios in One Plan",
          desc: "16:9 for YouTube, 9:16 for Reels and Shorts, 1:1 for feed posts — all included without extra cost.",
        },
        {
          title: "Director Presets Match Platform Tone",
          desc: "Slow Cinematic for YouTube essays, Handheld Kinetic for social, Dynamic Action for sports — pick once and the AI does the rest.",
        },
      ]}
      planCard={{
        name: "Creator",
        price: "$59",
        period: "/ mo",
        credits: 16,
        highlight: true,
        cta: "Upgrade to Creator",
        ctaHref: "/pricing",
        features: ["16 credits/mo", "Up to 16 scenes (~2 min)", "All director presets", "All aspect ratios", "No watermark"],
      }}
      ctaBanner={{
        title: "Start Creating Today",
        desc: "Demo mode is completely free. No sign-up required to see your first storyboard.",
        btnText: "Try It Free",
        btnHref: "/",
      }}
    />
    </>
  );
}

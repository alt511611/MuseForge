import SolutionPage from "../../../components/SolutionPage";
import { Building2, Megaphone, Film, Globe } from "lucide-react";

export const metadata = {
  title: "MuseForge for Ad Agencies — Corporate AI Video Studio",
  description: "Generate product launch videos, corporate presentations, and campaign concepts with MuseForge's multi-agent AI pipeline.",
};

export default function AgenciesPage() {
  return (
    <SolutionPage
      icon={Building2}
      accentColor="#7c3aed"
      badge="Ad Agencies & Corporate Comms"
      heading={<><span className="gradient-text">Pitch-Ready Video,</span><br /><span style={{ color: "#e2e8f0" }}>Generated in Minutes</span></>}
      subheading="From brand brief to cinematic storyboard — MuseForge's multi-agent pipeline handles scripting, visual design, and production so your team can focus on strategy."
      useCases={[
        {
          icon: Megaphone,
          title: "Product Launch Videos",
          desc: "Turn a product brief into a cinematic reveal — complete script, shot list, and assembled video ready for client review.",
          sample: "A luxury car emerges from desert dust at golden hour — slow cinematic preset, 16:9",
        },
        {
          icon: Building2,
          title: "Corporate Brand Films",
          desc: "Produce polished brand identity videos for pitches and investor decks without scheduling a full production crew.",
          sample: "Tech company headquarters montage — handheld kinetic preset, dynamic pacing",
        },
        {
          icon: Film,
          title: "Campaign Concept Reels",
          desc: "Visualise multiple creative directions in parallel — present 3 concepts in the time it used to take to storyboard 1.",
          sample: "Seasonal campaign — warm color grade, character locked across all 5 scenes",
        },
        {
          icon: Globe,
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
          title: "300 Credits / Month on Pro",
          desc: "Run 60+ full five-scene video projects per month for a flat $99. Ideal for agencies running multiple concurrent campaigns.",
        },
      ]}
      planCard={{
        name: "Pro",
        price: "$99",
        period: "/ mo",
        credits: 300,
        highlight: true,
        cta: "Upgrade to Pro",
        ctaHref: "/pricing",
        features: ["300 videos/mo", "Up to 5 scenes", "All director presets", "HD export", "3 team seats", "No watermark", "Priority render"],
      }}
      ctaBanner={{
        title: "Ready to Cut Production Time by 80%?",
        desc: "Try demo mode free — no API key, no credit card. See a full storyboard in under a minute.",
        btnText: "Try Demo Free",
        btnHref: "/",
      }}
    />
  );
}

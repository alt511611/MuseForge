import SolutionPage from "../../../components/SolutionPage";
import { Clapperboard, Eye, Film, Layers } from "lucide-react";

export const metadata = {
  title: "MuseForge for Filmmakers — AI Previsualization & Storyboard Tool",
  description: "Use MuseForge for shot previsualization, animatics, and storyboard generation on indie film projects.",
};

export default function FilmmakersPage() {
  return (
    <SolutionPage
      icon={<Clapperboard size={12} />}
      accentColor="#4f46e5"
      badge="Independent Filmmakers"
      heading={<><span className="gradient-text">Previsualize Any Scene</span><br /><span style={{ color: "#e2e8f0" }}>Before You Shoot It</span></>}
      subheading="Use MuseForge as your pre-production previsualization engine — generate shot-accurate storyboards and animatic-quality frame sequences without hiring a storyboard artist."
      useCases={[
        {
          icon: <Eye size={20} style={{ color: "#4f46e5" }} />,
          title: "Shot Previsualization",
          desc: "Translate a scene description into a multi-shot sequence with defined camera angles, lenses, and pacing — before a single real frame is captured.",
          sample: "Opening chase sequence — 5 shots, handheld kinetic preset, 2.39:1 anamorphic feel",
        },
        {
          icon: <Layers size={20} style={{ color: "#4f46e5" }} />,
          title: "Storyboard Generation",
          desc: "Get frame-by-frame visual reference for any scene. Share with your DP, production designer, or VFX supervisor in minutes.",
          sample: "Climactic confrontation scene — 4 shots, dramatic lighting, slow cinematic preset",
        },
        {
          icon: <Clapperboard size={20} style={{ color: "#4f46e5" }} />,
          title: "Short Film Concept Proof",
          desc: "Present a fully visualised 90-second short film concept to funders, festival selectors, or collaborators — long before production day.",
          sample: "Festival submission proof-of-concept — complete 3-scene short, noir mystery look",
        },
        {
          icon: <Film size={20} style={{ color: "#4f46e5" }} />,
          title: "Test Multiple Visual Styles",
          desc: "Generate the same scene in 3 different director presets and compare before committing to a visual language for your entire film.",
          sample: "Same scene in Slow Cinematic vs. Handheld Kinetic vs. Noir Mystery",
        },
      ]}
      differentiators={[
        {
          title: "No Subscription Required — Pay Per Project",
          desc: "Buy a credit pack for your current project. When the shoot wraps, stop paying. No recurring charges if you're between projects.",
        },
        {
          title: "Character Consistency for Casting Lookbooks",
          desc: "Upload a reference actor image and lock it across all scenes — ideal for casting presentations and production pitches.",
        },
        {
          title: "Director Presets Informed by Real Cinematography",
          desc: "Slow Cinematic (long lens, muted grade), Handheld Kinetic (verité energy), Noir Mystery (hard shadows, high contrast) — real directorial vocabulary built in.",
        },
        {
          title: "Export-Ready Storyboards",
          desc: "Every run produces a downloadable sequence of frame images. Import directly into your shot list or animatic editing timeline.",
        },
      ]}
      planCard={{
        name: "Credit Packages",
        price: "From $9",
        period: "",
        credits: null,
        highlight: false,
        cta: "Buy Credits",
        ctaHref: "/pricing",
        features: ["No subscription", "Credits never expire", "4 / 12 / 30 credit options", "Use any time, any project", "All director presets included"],
      }}
      ctaBanner={{
        title: "Previsualize Your Next Scene for Free",
        desc: "Demo mode generates a complete storyboard sequence at no cost. See exactly what the pipeline can do before spending a credit.",
        btnText: "Try Demo Mode",
        btnHref: "/",
      }}
    />
  );
}

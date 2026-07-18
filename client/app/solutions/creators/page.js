import SolutionPage from "../../../components/SolutionPage";
import { Users, Sparkles, Film, Zap } from "lucide-react";

export const metadata = {
  title: "MuseForge for Content Creators — AI Micro-Drama Studio",
  description: "Build micro-drama series, social video stories, and cinematic content at scale with MuseForge's AI pipeline.",
};

export default function CreatorsPage() {
  return (
    <SolutionPage
      icon={<Users size={12} />}
      accentColor="#6d28d9"
      badge="Content Creators & Solo Filmmakers"
      heading={<><span className="gradient-text">Your Entire Studio,</span><br /><span style={{ color: "#e2e8f0" }}>In One Prompt</span></>}
      subheading="Write an idea. MuseForge builds the script, designs the storyboard, generates every frame, and stitches a cinematic video — all in a few minutes."
      useCases={[
        {
          icon: <Film size={20} style={{ color: "#6d28d9" }} />,
          title: "Micro-Drama Series",
          desc: "Ship a new episode every day. Each run produces a complete short film — consistent characters, coherent plot, cinematic look.",
          sample: "Episode 3: A detective discovers a hidden room — noir mystery preset, 9:16 vertical",
        },
        {
          icon: <Sparkles size={20} style={{ color: "#6d28d9" }} />,
          title: "Social Media Story Arcs",
          desc: "Turn a trending topic or personal story into a shareable cinematic reel optimised for Instagram, TikTok, or YouTube Shorts.",
          sample: "Inspirational athlete journey — dynamic action preset, 1:1 square format",
        },
        {
          icon: <Zap size={20} style={{ color: "#6d28d9" }} />,
          title: "Rapid Concept Prototyping",
          desc: "Test 10 story ideas in the time it used to take to shoot 1. Validate audience hooks before investing in real production.",
          sample: "3 different romantic drama opening scenes — compare audience response",
        },
        {
          icon: <Users size={20} style={{ color: "#6d28d9" }} />,
          title: "Consistent Characters Across Episodes",
          desc: "Upload a single reference photo and MuseForge maintains that character's appearance in every scene of every episode.",
          sample: "Recurring protagonist across 5-episode arc — character lock active",
        },
      ]}
      differentiators={[
        {
          title: "25 Credits / Month for $49",
          desc: "Enough for about five full 5-scene videos per month — roughly $10/video all-in on Creator.",
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
        price: "$49",
        period: "/ mo",
        credits: 25,
        highlight: true,
        cta: "Upgrade to Creator",
        ctaHref: "/pricing",
        features: ["25 credits/mo", "Up to 3 scenes", "All director presets", "All aspect ratios", "No watermark"],
      }}
      ctaBanner={{
        title: "Start Creating Today",
        desc: "Demo mode is completely free. No sign-up required to see your first storyboard.",
        btnText: "Try It Free",
        btnHref: "/",
      }}
    />
  );
}

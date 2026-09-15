/**
 * The words on /solutions/creators — the page's content, separate from its layout.
 *
 * WHY THIS FILE EXISTS. This copy is now rendered twice: once as the HTML page
 * and once as the Markdown edition at /md/<locale>/solutions/creators, which is
 * what an assistant reads when somebody asks it about MuseForge. Two renderers
 * over one object is the only arrangement in which the plain-text edition
 * cannot say something the page does not — which is the line between
 * publishing a machine-readable copy and cloaking.
 *
 * Icons are names rather than elements: this module has to stay importable by
 * a route handler that renders no React at all. page.js maps them back.
 *
 * English only, like the pages themselves. The four segment pages were written
 * in English and are not translated (unlike the home page and /pricing, whose
 * copy comes from the locale dictionaries), so their Markdown editions are
 * English at every locale too.
 */

export const CONTENT = {
  title: "AI Micro-Drama Studio for Content Creators",
  description: "Build micro-drama series, social video stories, and cinematic content at scale with MuseForge's multi-agent AI pipeline.",
  badge: "Content Creators & Solo Filmmakers",
  /* The visible h1, in the two halves page.js styles it as: the lead
     takes the gradient, the rest stays plain. Stored rather than derived
     because the split is an editorial choice with no rule behind it --
     two of the four headings have no comma or any other mark to split
     on, and a heuristic that guessed one silently re-flowed them into a
     single gradient line. `headingText` joins them for the Markdown
     edition, which has no spans. */
  headingLead: "Your Entire Studio,",
  headingRest: "In One Prompt",
  headingText: "Your Entire Studio, In One Prompt",
  subheading: "Write an idea. MuseForge builds the script, designs the storyboard, generates every frame, and stitches a cinematic video — all in a few minutes.",
  accentColor: "var(--mf-violet-deep)",
  useCases: [
    {
      icon: "Film",
      title: "Micro-Drama Series",
      desc: "Ship a new episode every day. Each run produces a complete short film — consistent characters, coherent plot, cinematic look.",
      sample: "Episode 3: A detective discovers a hidden room — noir mystery preset, 9:16 vertical",
    },
    {
      icon: "Sparkles",
      title: "Social Media Story Arcs",
      desc: "Turn a trending topic or personal story into a shareable cinematic reel optimised for Instagram, TikTok, or YouTube Shorts.",
      sample: "Inspirational athlete journey — dynamic action preset, 1:1 square format",
    },
    {
      icon: "Zap",
      title: "Rapid Concept Prototyping",
      desc: "Test 10 story ideas in the time it used to take to shoot 1. Validate audience hooks before investing in real production.",
      sample: "3 different romantic drama opening scenes — compare audience response",
    },
    {
      icon: "Users",
      title: "Consistent Characters Across Episodes",
      desc: "Upload a single reference photo and MuseForge maintains that character's appearance in every scene of every episode.",
      sample: "Recurring protagonist across 5-episode arc — character lock active",
    },
  ],
  differentiators: [
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
  ],
  planCard: {
    name: "Creator",
    price: "$59",
    period: "/ mo",
    credits: 16,
    highlight: true,
    cta: "Upgrade to Creator",
    ctaHref: "/pricing",
    features: ["16 credits/mo", "Up to 16 scenes (~2 min)", "All director presets", "All aspect ratios", "No watermark"],
  },
  ctaBanner: {
    title: "Start Creating Today",
    desc: "Demo mode is completely free. No sign-up required to see your first storyboard.",
    btnText: "Try It Free",
    btnHref: "/",
  },
};

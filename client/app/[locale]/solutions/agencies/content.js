/**
 * The words on /solutions/agencies — the page's content, separate from its layout.
 *
 * WHY THIS FILE EXISTS. This copy is now rendered twice: once as the HTML page
 * and once as the Markdown edition at /md/<locale>/solutions/agencies, which is
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
  title: "Corporate AI Video Studio for Ad Agencies",
  description: "Generate product launch videos, corporate brand films, and campaign concepts with MuseForge's multi-agent AI pipeline.",
  badge: "Ad Agencies & Corporate Comms",
  /* The visible h1, in the two halves page.js styles it as: the lead
     takes the gradient, the rest stays plain. Stored rather than derived
     because the split is an editorial choice with no rule behind it --
     two of the four headings have no comma or any other mark to split
     on, and a heuristic that guessed one silently re-flowed them into a
     single gradient line. `headingText` joins them for the Markdown
     edition, which has no spans. */
  headingLead: "Pitch-Ready Video,",
  headingRest: "Generated in Minutes",
  headingText: "Pitch-Ready Video, Generated in Minutes",
  subheading: "From brand brief to cinematic storyboard — MuseForge's multi-agent pipeline handles scripting, visual design, and production so your team can focus on strategy.",
  accentColor: "var(--mf-violet)",
  useCases: [
    {
      icon: "Megaphone",
      title: "Product Launch Videos",
      desc: "Turn a product brief into a cinematic reveal — complete script, shot list, and assembled video ready for client review.",
      sample: "A luxury car emerges from desert dust at golden hour — slow cinematic preset, 16:9",
    },
    {
      icon: "Building2",
      title: "Corporate Brand Films",
      desc: "Produce polished brand identity videos for pitches and investor decks without scheduling a full production crew.",
      sample: "Tech company headquarters montage — handheld kinetic preset, dynamic pacing",
    },
    {
      icon: "Film",
      title: "Campaign Concept Reels",
      desc: "Visualise multiple creative directions in parallel — present 3 concepts in the time it used to take to storyboard 1.",
      sample: "Seasonal campaign — warm color grade, character locked across all 5 scenes",
    },
    {
      icon: "Globe",
      title: "Multi-Market Localisation",
      desc: "Generate region-specific visual concepts with different cultural contexts — same brief, different executions.",
      sample: "Same product story adapted for 3 different visual markets",
    },
  ],
  differentiators: [
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
  ],
  planCard: {
    name: "Pro",
    price: "$129",
    period: "/ mo",
    credits: 36,
    highlight: true,
    cta: "Upgrade to Pro",
    ctaHref: "/pricing",
    features: ["36 credits/mo", "Up to 24 scenes (~3 min)", "All director presets", "HD export", "No watermark"],
  },
  ctaBanner: {
    title: "Ready to Cut Production Time by 80%?",
    desc: "Try demo mode free — no API key, no credit card. See a full storyboard in under a minute.",
    btnText: "Try Demo Free",
    btnHref: "/",
  },
};

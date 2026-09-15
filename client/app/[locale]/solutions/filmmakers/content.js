/**
 * The words on /solutions/filmmakers — the page's content, separate from its layout.
 *
 * WHY THIS FILE EXISTS. This copy is now rendered twice: once as the HTML page
 * and once as the Markdown edition at /md/<locale>/solutions/filmmakers, which is
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
  title: "AI Previsualization & Storyboard Tool for Filmmakers",
  description: "Use MuseForge for shot previsualization, animatics, and storyboard generation on indie film projects — no storyboard artist required.",
  badge: "Independent Filmmakers",
  /* The visible h1, in the two halves page.js styles it as: the lead
     takes the gradient, the rest stays plain. Stored rather than derived
     because the split is an editorial choice with no rule behind it --
     two of the four headings have no comma or any other mark to split
     on, and a heuristic that guessed one silently re-flowed them into a
     single gradient line. `headingText` joins them for the Markdown
     edition, which has no spans. */
  headingLead: "Previsualize Any Scene",
  headingRest: "Before You Shoot It",
  headingText: "Previsualize Any Scene Before You Shoot It",
  subheading: "Use MuseForge as your pre-production previsualization engine — generate shot-accurate storyboards and animatic-quality frame sequences without hiring a storyboard artist.",
  accentColor: "#4f46e5",
  useCases: [
    {
      icon: "Eye",
      title: "Shot Previsualization",
      desc: "Translate a scene description into a multi-shot sequence with defined camera angles, lenses, and pacing — before a single real frame is captured.",
      sample: "Opening chase sequence — 5 shots, handheld kinetic preset, 2.39:1 anamorphic feel",
    },
    {
      icon: "Layers",
      title: "Storyboard Generation",
      desc: "Get frame-by-frame visual reference for any scene. Share with your DP, production designer, or VFX supervisor in minutes.",
      sample: "Climactic confrontation scene — 4 shots, dramatic lighting, slow cinematic preset",
    },
    {
      icon: "Clapperboard",
      title: "Short Film Concept Proof",
      desc: "Present a fully visualised 90-second short film concept to funders, festival selectors, or collaborators — long before production day.",
      sample: "Festival submission proof-of-concept — complete 3-scene short, noir mystery look",
    },
    {
      icon: "Film",
      title: "Test Multiple Visual Styles",
      desc: "Generate the same scene in 3 different director presets and compare before committing to a visual language for your entire film.",
      sample: "Same scene in Slow Cinematic vs. Handheld Kinetic vs. Noir Mystery",
    },
  ],
  differentiators: [
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
  ],
  planCard: {
    name: "Credit Packages",
    price: "From $19",
    period: "",
    credits: null,
    highlight: false,
    cta: "Buy Credits",
    ctaHref: "/pricing",
    features: ["No subscription", "Valid 30 days from purchase", "4 / 12 / 26 credit options", "Any project, any time", "All director presets included"],
  },
  ctaBanner: {
    title: "Previsualize Your Next Scene for Free",
    desc: "Demo mode generates a complete storyboard sequence at no cost. See exactly what the pipeline can do before spending a credit.",
    btnText: "Try Demo Mode",
    btnHref: "/",
  },
};

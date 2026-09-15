/**
 * The words on /solutions/education — the page's content, separate from its layout.
 *
 * WHY THIS FILE EXISTS. This copy is now rendered twice: once as the HTML page
 * and once as the Markdown edition at /md/<locale>/solutions/education, which is
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
  title: "AI Video for Schools & Universities",
  description: "Create educational explainer videos, support student film projects, and produce institutional promotional content with MuseForge.",
  badge: "Educational Institutions",
  /* The visible h1, in the two halves page.js styles it as: the lead
     takes the gradient, the rest stays plain. Stored rather than derived
     because the split is an editorial choice with no rule behind it --
     two of the four headings have no comma or any other mark to split
     on, and a heuristic that guessed one silently re-flowed them into a
     single gradient line. `headingText` joins them for the Markdown
     edition, which has no spans. */
  headingLead: "AI Video for",
  headingRest: "Classrooms & Campuses",
  headingText: "AI Video for Classrooms & Campuses",
  subheading: "Give students a professional-grade AI studio for their projects. Create institutional promotional content without a production budget. MuseForge scales from a single teacher to an entire university.",
  accentColor: "#0891b2",
  useCases: [
    {
      icon: "GraduationCap",
      title: "Student Film Projects",
      desc: "Students write a story idea; MuseForge generates a complete short film — a powerful introduction to AI-assisted storytelling and production.",
      sample: "Student sci-fi short: 'The Last Signal' — 3 scenes, cinematic preset",
    },
    {
      icon: "BookOpen",
      title: "Educational Explainer Videos",
      desc: "Instructors generate visual explainers for complex topics — history re-enactments, scientific concepts, or literature adaptations.",
      sample: "History lesson visualization: Roman Senate chamber — slow cinematic, 16:9",
    },
    {
      icon: "Users",
      title: "Campus Promotional Content",
      desc: "Produce campus tour teasers, department showcases, and recruitment videos without booking a film crew.",
      sample: "University open day promo — warm cinematic look, campus characters",
    },
    {
      icon: "Lightbulb",
      title: "Creative Media Curriculum",
      desc: "Use MuseForge as a hands-on tool in digital media, film studies, or creative writing classes — students learn AI pipeline fundamentals by doing.",
      sample: "Class exercise: 20 students each generate a different genre short in one session",
    },
  ],
  differentiators: [
    {
      title: "Demo Mode — Zero Cost for Classroom Exploration",
      desc: "Students can run the full pipeline and see a complete storyboard without spending any credits. Ideal for introductory workshops.",
    },
    {
      title: "Creator Plan for Individual Teachers — $59/mo",
      desc: "16 credits per month covers a term of student projects — about three 5-scene videos per cohort.",
    },
    {
      title: "Enterprise Licence for Campus-Wide Deployment",
      desc: "Custom credit volume, SSO integration, and a dedicated account manager. Contact us to discuss institution-wide pricing.",
    },
    {
      title: "Safe, Ethical AI Output",
      desc: "MuseForge produces controlled, script-guided visuals from user-written ideas — appropriate for supervised educational use.",
    },
  ],
  planCard: {
    name: "Creator (Individual Educator)",
    price: "$59",
    period: "/ mo",
    credits: 16,
    highlight: false,
    cta: "Start with Creator",
    ctaHref: "/pricing",
    features: ["16 credits/mo", "Up to 16 scenes (~2 min)", "All presets", "All ratios", "No watermark"],
  },
  ctaBanner: {
    title: "Need a Campus-Wide Licence?",
    desc: "We offer custom pricing, SSO, and onboarding for universities and school networks. Let's talk.",
    btnText: "Contact Enterprise Sales",
    btnHref: "mailto:enterprise@museforge.studio",
  },
};

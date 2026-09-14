export default {
  title: "Choosing an AI video generator: the questions that actually matter",
  description:
    "Resolution and model names are the specs vendors compete on. The things that decide whether you can finish a film are continuity, retake granularity and what happens to your work after the render ends.",
  blocks: [
    {
      t: "tldr",
      items: [
        "Demo reels are chosen from hundreds of attempts. Judge a tool by its **second** output, not its best one.",
        "The decisive questions are continuity across shots, whether you can re-shoot one shot, and whether anything survives after the job finishes.",
        "Per-clip pricing is misleading until you know your retake rate — a cheap clip you generate four times is not cheap.",
        "Resolution is the least important spec on the page. 4K that no model natively renders is an upscale, and should be labelled as one.",
      ],
    },
    {
      t: "p",
      text: "Every AI video tool's landing page shows footage that looks extraordinary, and all of it is real. It is also the survivor of a selection process you do not see: someone generated the shot many times and published the one that worked. That is not dishonest, but it means the reel tells you about the ceiling, and what you need to know is the floor.",
    },

    { t: "h2", text: "The seven questions" },
    {
      t: "table",
      caption: "Ask these before the free credits run out, in roughly this order of importance.",
      head: ["Question", "Why it decides the outcome"],
      rows: [
        [
          "Does a character stay the same across shots?",
          "The most common reason a finished film is unusable. Ask specifically whether the tool accepts a reference image on every shot, or only re-describes the character in text.",
        ],
        [
          "Can I re-shoot one shot?",
          "You will reject roughly one shot in five. If the smallest re-render unit is the whole scene or the whole film, your real cost is several times the list price.",
        ],
        [
          "Does anything survive the render?",
          "If the cast, the look and the story state are discarded when the job ends, you can make films but not a series — and the series is where the economics are.",
        ],
        [
          "Can I see frames before paying for motion?",
          "Stills are far cheaper than clips and expose nearly every error. A tool that goes straight to video makes each mistake cost full price.",
        ],
        [
          "What happens when a shot fails?",
          "Long generations fail sometimes. Retry with backoff, a fallback model and a resumable job are the difference between a hiccup and a lost hour.",
        ],
        [
          "How many vendor accounts do I need?",
          "Pipelines that split video, voice, music and lip sync across providers hand you several bills, several rate limits and several outages.",
        ],
        [
          "Is the 4K real?",
          "No current video model renders 4K natively. A 4K deliverable is an upscale. That is fine — a tool that says so is telling you the truth about the rest of its spec sheet too.",
        ],
      ],
    },

    { t: "h2", text: "How to run a fair trial" },
    {
      t: "steps",
      name: "How to evaluate an AI video generator in under an hour",
      description: "A short test designed to surface the failures that matter rather than the ones the demo reel already answered.",
      totalTime: "PT45M",
      items: [
        {
          name: "Generate the same character twice, in different shots",
          text: "Not the same prompt twice — two different shots of one person. This is the test almost every tool fails, and it takes two minutes. If the faces do not match, nothing else on the spec sheet will save the project.",
        },
        {
          name: "Break something on purpose, then fix one shot",
          text: "Produce a short sequence, pick one shot, and try to re-shoot only that shot. Note what it costs and whether the rest of the sequence survives untouched.",
        },
        {
          name: "Come back tomorrow and continue",
          text: "Close the tab, return the next day, and try to make a second episode with the same characters. Whether that is possible at all is the single largest difference between tools, and it never appears in a feature comparison.",
        },
        {
          name: "Check the failure path",
          text: "Run a long job and watch what the interface does while it works. A progress bar with no log tells you nothing when it stalls; a live agent log tells you which stage is running and whether it retried.",
        },
        {
          name: "Do the retake arithmetic",
          text: "Take the per-clip price, multiply by your observed retake rate from step two, and compare that against a monthly plan. The honest cost of a two-minute film is the number you get here, not the list price.",
        },
      ],
    },

    { t: "h2", text: "Specs that matter less than they look" },
    {
      t: "ul",
      items: [
        "**The underlying model's name.** Most tools route to the same handful of video models. What differs is the pipeline around them, and that is what you are actually buying.",
        "**Maximum clip length.** Long single clips are rarely what a film needs — it needs many short ones that cut together. Clip length is a constraint, not a feature.",
        "**Resolution.** Above 1080p, delivery resolution is an upscale decision. It affects file size more than it affects whether the film is watchable.",
        "**Style preset count.** Thirty presets that each shift the colour grade are one feature. What matters is whether a preset also changes pacing, lens and coverage — that is a director, not a filter.",
      ],
    },
    {
      t: "callout",
      tone: "warn",
      title: "Watch for the free trial that hides the real workflow",
      text: "A trial limited to single clips cannot answer any of the questions above, because all of them are about what happens across shots. If the free tier only generates one clip at a time, you have not tested the product — you have tested the model it calls.",
    },

    { t: "h2", text: "Where MuseForge sits" },
    {
      t: "p",
      text: "For transparency about the obvious bias: this is MuseForge's blog, and the questions above are the ones MuseForge is built around — a portrait locked once and reused on every frame, a single beat re-shootable without re-rendering the take, a series that carries its cast and locks into the next episode, storyboard frames approved before motion is paid for, one provider for video, voice, music and lip sync, and a 4K tier that says in the job record that it is an upscale.",
    },
    {
      t: "p",
      text: "You should still run the trial in the section above on us, and on whatever else you are considering. The [demo mode](/) runs the entire pipeline without an API key, which exists precisely so the second and third questions can be answered before anyone pays anything.",
    },

    {
      t: "faq",
      items: [
        {
          q: "What is the most important feature in an AI video generator?",
          a: "Character consistency across shots. Every other shortcoming produces a worse film; this one produces an unusable one, because an audience cannot follow a story whose protagonist changes face between cuts.",
        },
        {
          q: "Why does AI video cost more than the advertised per-clip price?",
          a: "Because of retakes. A realistic rejection rate is around one shot in five, so the effective cost of a finished film is roughly twenty percent above the naive clip count — more if the smallest re-render unit is a whole scene rather than a single shot.",
        },
        {
          q: "Do AI video tools really generate 4K?",
          a: "No current video model renders 4K natively; a 4K deliverable is produced by upscaling a lower-resolution render. This is a normal and acceptable practice — the thing to look for is whether the tool states it rather than implying native 4K.",
        },
        {
          q: "Should I pick the tool with the newest model?",
          a: "Rarely. Most products route to the same small set of video models, so the model name is close to a constant across the market. The differences that affect your finished film come from the pipeline: consistency handling, retake granularity, and what state survives a job.",
        },
        {
          q: "How can I test an AI video tool without spending much?",
          a: "Generate two different shots of one character and compare the faces; then try to re-shoot a single shot from a finished sequence. Those two tests take a few minutes and answer more than an hour of browsing feature lists.",
        },
        {
          q: "Is it better to use one tool or combine several?",
          a: "Combining tools gives you more control over each stage and more accounts, rate limits and failure points to manage. For a single maker producing a series on a schedule, a single pipeline usually wins; for a studio with a dedicated post team, assembling best-in-class stages can be worth the overhead.",
        },
      ],
    },

    {
      t: "cta",
      title: "Run the two-minute test",
      text: "Generate two shots of the same character in demo mode and see whether the faces match. No key, no card.",
      button: "Open the demo",
      href: "/",
    },
  ],
};

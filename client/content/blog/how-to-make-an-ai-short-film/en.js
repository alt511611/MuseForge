export default {
  title: "How to make an AI short film from a single idea",
  description:
    "The full path from one sentence to a finished two-minute film: story, cast, shot list, frames, motion and sound — and the decisions at each stage that decide whether the result looks made or generated.",
  blocks: [
    {
      t: "tldr",
      items: [
        "A watchable AI short is built in six stages, and five of them happen before any video is generated.",
        "Write the story first and the prompts second. A film that was prompted rather than written reads as a slideshow of nice frames.",
        "Lock the cast before the first shot — see [the consistency guide](/blog/ai-video-character-consistency).",
        "Budget for retakes: expect to re-shoot roughly one shot in five, so choose a tool that lets you redo one shot rather than the whole film.",
      ],
    },
    {
      t: "p",
      text: "\"Make me a film about a detective who finds a hidden room\" is an idea, not a film. What separates the two is about forty decisions — how long each shot holds, whose face we are on when the line lands, whether the room is revealed in one move or three. Generating video is the easy part. This is the guide to the other part.",
    },

    { t: "h2", text: "The six stages" },
    {
      t: "steps",
      name: "How to make an AI short film",
      description:
        "Six stages from a one-sentence idea to a finished, graded short — in the order that keeps each stage's mistakes cheap.",
      totalTime: "PT45M",
      items: [
        {
          name: "Write the premise as a change, not a subject",
          text: "\"A detective finds a hidden room\" is a subject. \"A detective who trusts her partner finds a room that proves she shouldn't\" is a change. The second one has an ending; the first one only has a middle. Every downstream stage gets easier when the premise already knows where it lands.",
        },
        {
          name: "Break it into scenes, and give each one a job",
          text: "Three to six scenes for a two-minute film. Each scene does exactly one thing to the story — establishes, complicates, turns, resolves. A scene that does nothing is the scene you will cut later, so cut it now while it is free.",
        },
        {
          name: "Cast and lock before you shoot",
          text: "Generate one reference portrait per character and fix the wardrobe wording. Doing this after the first scene is generated means scene one has a different lead than the rest of the film, and scene one is the one people judge you on.",
        },
        {
          name: "Storyboard every shot as a still",
          text: "Generate the frames before the motion. Stills are an order of magnitude cheaper than video, and nearly every mistake you are going to make — wrong wardrobe, wrong room, wrong eyeline, a stranger in the background — is visible in the still. Fix it there.",
        },
        {
          name: "Generate motion only from approved frames",
          text: "Animate from the stills you accepted, one shot at a time, with the shot's own action described. This is the expensive stage, which is precisely why it comes fifth rather than first.",
        },
        {
          name: "Cut, then score",
          text: "Assemble in story order, trim every shot to the moment it stops earning its length, and add sound last. Music over a loose cut hides nothing; it just makes a loose cut louder.",
        },
      ],
    },

    { t: "h2", text: "How long should each shot be?" },
    {
      t: "p",
      text: "Most AI shorts are cut too slow, because the maker is admiring the frame rather than watching the film. A useful default: a shot holds for as long as it delivers new information, and one beat longer if it carries emotion.",
    },
    {
      t: "keyfacts",
      items: [
        { term: "Establishing shot", value: "4–6 seconds. Long enough to read the geography, not long enough to study it." },
        { term: "Dialogue shot", value: "2–4 seconds per line. Cut on the thought, not on the silence after it." },
        { term: "Action shot", value: "1.5–3 seconds. Motion reads fast; holding it makes it look looped." },
        { term: "Emotional beat", value: "3–5 seconds. The one place a long hold is doing work." },
        { term: "Two-minute film", value: "Roughly 25–40 shots. If you have 12, it is a slideshow; if you have 90, it is a trailer." },
      ],
    },

    { t: "h2", text: "The mistakes that make a film look generated" },
    {
      t: "ul",
      items: [
        "**Every shot is the same size.** Real coverage alternates wide, medium and close. Six consecutive medium shots is the strongest tell that nobody made framing decisions.",
        "**Everyone looks at the camera.** Actors look at each other. A character addressing the lens turns a drama into a piece to camera, and models do this by default unless told not to.",
        "**The light moves between cuts.** Two shots inside one conversation must share a light source and a direction. This is the continuity error audiences feel without being able to name.",
        "**The cut is on the pause.** Cutting after the line has landed and the actor is just standing there adds half a second of dead air to every shot. Over thirty shots that is fifteen seconds of nothing.",
        "**The ending just stops.** Generated films tend to run out rather than end. Decide the last frame before you generate the first.",
      ],
    },
    {
      t: "callout",
      tone: "warn",
      title: "Crossing the line",
      text: "If shot A has character X on the left looking right, shot B must not put X on the right looking left. Breaking the 180° axis mid-conversation makes two people appear to face the same way, and the scene stops reading as a conversation. Say which side each character is on, in every prompt of the scene.",
    },

    { t: "h2", text: "What this costs, in time and in credits" },
    {
      t: "p",
      text: "The expensive resource is not the render, it is the re-render. A first pass that produces thirty usable shots out of thirty is not a thing that happens; plan on re-shooting roughly one in five. That number is the reason the storyboard stage exists — a rejected still costs a fraction of a rejected clip.",
    },
    {
      t: "p",
      text: "It is also the reason to check, before you start, whether your tool can re-shoot **one shot** or only the whole scene. Re-generating a five-scene film to fix a single bad framing is the difference between a two-hour project and a two-day one. In [MuseForge](/) a single beat can be re-shot from its own brief while the rest of the take is kept, and the earlier version stays restorable.",
    },

    {
      t: "faq",
      items: [
        {
          q: "How long does it take to make an AI short film?",
          a: "For a two-minute film: roughly 30–60 minutes of writing and shot planning, and a similar amount of generation and revision time. The generation itself is mostly waiting; the hour that decides quality is the one spent on the scene breakdown and the storyboard.",
        },
        {
          q: "Should I write the script or generate it?",
          a: "Generate a draft if you want, but edit it as a writer would. The reliable failure of a generated script is that every scene is equally important, because the model has no sense of which beat the film is actually about. Deciding that is the job you cannot delegate.",
        },
        {
          q: "Do I need to generate still frames before video?",
          a: "It is not required, but it is the single largest cost saver. Stills are far cheaper than clips, and most errors — wardrobe, setting, eyeline, an extra person in frame — are fully visible in a still. Approving frames first turns expensive mistakes into cheap ones.",
        },
        {
          q: "How many scenes should a two-minute AI film have?",
          a: "Three to six. Fewer than three and there is no structure to follow; more than six and each scene gets under twenty seconds, which is not long enough to establish a place and do something in it.",
        },
        {
          q: "Why does my AI film look like a slideshow?",
          a: "Usually three causes at once: every shot is the same size, every shot is the same length, and nothing moves within the frame. Vary the shot sizes, cut the dead air at the end of each shot, and make sure each clip has motion inside it rather than only camera drift.",
        },
        {
          q: "Can I add dialogue and music to an AI short film?",
          a: "Yes, and the order matters: cut the picture first, then add sound. A cut that only works once the music is on top is a cut that does not work.",
        },
      ],
    },

    {
      t: "cta",
      title: "Start with the storyboard",
      text: "MuseForge's demo mode runs the full pipeline — script, cast, storyboard, frames — before you spend anything.",
      button: "Generate a storyboard",
      href: "/",
    },
  ],
};

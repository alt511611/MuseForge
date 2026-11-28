export default {
  metaTitle: "AI filmmaking: what works, where it breaks",
  metaDescription:
    "AI filmmaking stage by stage: what it does well, the four failures that decide whether a film is watchable, and how it differs from a clip generator.",
  title: "AI filmmaking: what it can make today, and where it still breaks",
  description:
    "What AI filmmaking actually means stage by stage, the kinds of film it already does well, the four failures that still decide whether a film is watchable, and the difference between an AI film maker and a clip generator.",
  blocks: [
    {
      t: "tldr",
      items: [
        "AI filmmaking is making a film in which generative models produce the picture, the sound or the script, while a person still makes the decisions a director makes.",
        "It already works for short narrative films, previsualisation, pitch films and episodic micro-dramas. Feature-length work is still assembled from many short pieces.",
        "What breaks is rarely image quality. It is continuity: faces, wardrobe and rooms that change between shots.",
        "A clip generator gives you shots. An AI film maker gives you a film — script, cast, storyboard, edit and sound, held together as one project.",
      ],
    },
    {
      t: "p",
      text: "AI filmmaking is the practice of making a film in which generative models produce some or all of the material — the script draft, the frames, the motion, the voices, the score — while a person keeps the decisions that make it a film: what the story is about, which moment each shot exists for, and what gets cut. The models do the labour that used to need a crew. They do not do the directing, and every AI film that reads as made rather than generated is one where somebody did.",
    },

    { t: "h2", text: "What AI does at each stage of a film" },
    {
      t: "p",
      text: "A film is still made in the same order it always was. What changes is who, or what, does the work at each stage — and how cheap it is to change your mind.",
    },
    {
      t: "keyfacts",
      items: [
        {
          term: "Script",
          value: "A language model drafts scenes, dialogue and a shot list from a premise. Useful as a first draft; it needs a writer's edit, because a model treats every beat as equally important.",
        },
        {
          term: "Casting",
          value: "One reference portrait per character is generated or uploaded. This image, not the text description, is what keeps a face consistent later.",
        },
        {
          term: "Storyboard",
          value: "Every shot is generated as a still first. Stills are far cheaper than video and show almost every mistake — see [the storyboard guide](/blog/ai-storyboard-generator).",
        },
        {
          term: "Shots",
          value: "A video model animates each approved frame into a short clip with its own action. This is the expensive stage.",
        },
        {
          term: "Voice and lip sync",
          value: "Dialogue is synthesised per character and, where a face is speaking on screen, the mouth is matched to it.",
        },
        {
          term: "Music and edit",
          value: "Shots are cut in story order and trimmed to the moment they stop earning their length; a score is generated or chosen last.",
        },
      ],
    },

    { t: "h2", text: "What AI filmmaking already does well" },
    {
      t: "ul",
      items: [
        "**Short narrative films.** One to four minutes, three to six scenes, a small cast. This is the format the tools are built around today — see [how to make an AI short film](/blog/how-to-make-an-ai-short-film).",
        "**Episodic micro-dramas.** Vertical series with recurring characters, where each episode is short and the cast carries over. The [micro-drama playbook](/blog/micro-drama-series-playbook) covers the format.",
        "**Previsualisation.** A director or agency sees a sequence cut together before anything is shot or budgeted, and changes it for the price of a few stills.",
        "**Pitch and concept films.** A client-facing film that shows the idea moving, made in an afternoon instead of commissioned for a week.",
        "**Teaching film language.** Students change one variable — shot size, lens, pacing — and see the same scene cut differently.",
      ],
    },

    { t: "h2", text: "Where it still breaks" },
    {
      t: "table",
      caption: "The failures that decide whether an AI film is watchable, in the order you will meet them.",
      head: ["Failure", "Why it happens", "What fixes it"],
      rows: [
        [
          "The lead looks different in every shot",
          "Each shot is generated independently from a text description, and text cannot pin a face.",
          "One reference portrait reused on every frame. The full mechanism is in [the character consistency guide](/blog/ai-video-character-consistency).",
        ],
        [
          "Wardrobe and rooms drift",
          "Costume and set are re-described per shot, so small wording changes become visible changes.",
          "Lock the wording for wardrobe, location and light once, and reuse it verbatim across the shot list.",
        ],
        [
          "It feels like a slideshow",
          "Every shot is the same size, the same length, and nothing moves inside the frame.",
          "Vary shot sizes, cut dead air from the end of each clip, and describe an action for every shot.",
        ],
        [
          "One bad shot costs the whole scene",
          "The tool's smallest re-render unit is the scene or the film.",
          "Choose a tool that re-shoots a single shot and leaves the rest untouched.",
        ],
      ],
    },
    {
      t: "callout",
      tone: "note",
      title: "Image quality is no longer the bottleneck",
      text: "Most tools now route to a small number of capable video models, so individual frames look good almost everywhere. What separates a finished film from a folder of clips is the pipeline around those models: continuity, retakes and an edit.",
    },

    { t: "h2", text: "AI film maker or AI video generator?" },
    {
      t: "p",
      text: "The two names get used interchangeably, and they describe different products. An **AI video generator** turns a prompt into a clip: you get one shot, and assembling shots into a film is your job. An **AI film maker** starts from a story and returns a film: it writes the scenes, holds the cast and the look across every shot, and cuts the result with sound. If what you want at the end is something people watch from start to finish, the second is the one to evaluate — and [these are the questions that separate them](/blog/choosing-an-ai-video-generator).",
    },
    {
      t: "p",
      text: "MuseForge is built as the second kind. You type one idea; a Screenwriter agent drafts the script, which you can review and edit before anything is charged; a Storyboard Artist plans the shots; every frame is generated from each character's locked portrait; and the scenes are animated, voiced, scored and cut into one film. A scene that misses can be re-shot on its own.",
    },

    {
      t: "faq",
      items: [
        {
          q: "What is AI filmmaking?",
          a: "Making a film in which generative AI produces some or all of the script, images, motion, voices or music, while a person directs: chooses the story, approves each shot and decides the cut.",
        },
        {
          q: "Can you make a full movie with AI?",
          a: "Short films, yes — one to a few minutes is what current tools are designed for. A feature-length film is possible only as a long project assembled from many short scenes, and continuity across that length is still the hard part.",
        },
        {
          q: "How do I make an AI movie?",
          a: "Write the premise as a change, break it into three to six scenes, lock a reference portrait for each character, storyboard every shot as a still, animate only the frames you approve, then cut and score. [The step-by-step guide](/blog/how-to-make-an-ai-short-film) walks through each stage.",
        },
        {
          q: "Is AI filmmaking real filmmaking?",
          a: "The decisions are the same ones a director makes — what each shot is for, how long it holds, what gets cut. The labour is different. A film that was only prompted, with nobody making those decisions, usually looks like it.",
        },
        {
          q: "Who owns a film made with AI?",
          a: "It depends on the tool's terms and on the law where you are. On MuseForge, the videos you generate are licensed to you for personal and commercial use. Copyright protection for purely machine-generated material is limited in some jurisdictions, including the United States, so the human choices — script, selection, edit — are worth keeping a record of.",
        },
        {
          q: "How much does AI filmmaking cost?",
          a: "Tools price per clip, per second or per credit. The honest cost includes retakes: expect to re-generate roughly one shot in five. On MuseForge one credit is ten seconds of finished film, and the free plan includes monthly credits plus an unlimited demo mode — [pricing](/pricing) has the current plans.",
        },
      ],
    },

    {
      t: "cta",
      title: "Make a short film from one sentence",
      text: "Demo mode runs the whole pipeline — script, cast, storyboard, frames — before you spend a credit.",
      button: "Start with an idea",
      href: "/",
    },
  ],
};

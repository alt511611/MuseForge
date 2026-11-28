export default {
  title: "Script to video AI: three kinds of tool, and which one makes a film",
  description:
    "\"Script to video\" names three different products: avatar presenters, stock-footage editors and generative film makers. What each one turns your script into, how to prepare a script so it survives the trip, and where the script stage usually goes wrong.",
  blocks: [
    {
      t: "tldr",
      items: [
        "\"Script to video\" covers three different tools: an avatar reads your script, stock footage is matched to it, or every scene is generated as film with a cast.",
        "Pick by what the video is for. Training and explainers suit avatars; social posts suit stock footage; a story with characters needs a generative film maker.",
        "A script becomes better video when each scene has one location, each character is described once, and every action line is something a camera can see.",
        "Review the script before anything renders. Edits to text are free; edits to finished video are the most expensive change you can make.",
      ],
    },
    {
      t: "p",
      text: "Script to video AI is software that takes written text and returns a finished video: it splits the script into scenes, produces a picture for each one, adds voice and music, and exports the result. Under that one name sit three products that do very different things with your script, and choosing the wrong kind is the usual reason the result disappoints. The first question is not which tool is best, but which kind of video you are making.",
    },

    { t: "h2", text: "The three kinds of script to video tool" },
    {
      t: "table",
      caption: "What happens to the same script in each kind of tool.",
      head: ["Kind", "What your script becomes", "Good for", "Weak at"],
      rows: [
        [
          "Avatar presenter",
          "A digital presenter reads the script to camera, with slides or b-roll behind.",
          "Training, onboarding, product explainers, multilingual versions of one talk.",
          "Anything with more than one character, a location or a story.",
        ],
        [
          "Stock footage editor",
          "Each sentence is matched to library clips or generated images, with a voiceover on top.",
          "Social posts, listicles, blog-to-video, narrated summaries.",
          "Recurring characters — the footage never shows the same person twice.",
        ],
        [
          "Generative film maker",
          "Each scene is generated as film: a cast, a setting, shots with action, dialogue and a cut.",
          "Short films, micro-drama series, pitch films, previsualisation.",
          "Talking-head explainers, where a presenter is faster and cheaper.",
        ],
      ],
    },
    {
      t: "p",
      text: "If the script has characters who need to look like themselves from the first shot to the last, only the third kind is built for it. The other two are excellent at what they do; continuity of a cast is not part of it.",
    },

    { t: "h2", text: "How to prepare a script for AI video" },
    {
      t: "steps",
      name: "How to prepare a script for script to video AI",
      description:
        "Five edits that make a script survive the trip into generated video, in the order that catches the most problems first.",
      totalTime: "PT20M",
      items: [
        {
          name: "Give every scene exactly one location and one time of day",
          text: "A scene that moves from the kitchen to the street is two scenes to a video model. Split it, and name the place and the light at the top of each one. Most drift in setting starts with a scene that never said where it was.",
        },
        {
          name: "Describe each character once, physically, and reuse the wording",
          text: "Age, build, hair, wardrobe — in one fixed line per character. Do not re-describe them scene by scene; small changes in wording become visible changes on screen. A reference portrait does the rest, as [the consistency guide](/blog/ai-video-character-consistency) explains.",
        },
        {
          name: "Rewrite action lines as things a camera can see",
          text: "\"She realises he lied\" cannot be filmed. \"She stops reading, looks at the door, and puts the letter face down\" can. Interior states have to be translated into behaviour before any model can show them.",
        },
        {
          name: "Keep dialogue short and attributed",
          text: "One or two lines per beat, each with a clear speaker. Long speeches become long static shots, and unattributed lines cannot be voiced or lip-synced to the right face.",
        },
        {
          name: "Mark the one beat each scene exists for",
          text: "Every scene has a moment it is about. Mark it, so the shot plan spends its close-up there. A generated shot list without that mark treats every line as equally important, which is why it reads flat.",
        },
      ],
    },

    { t: "h2", text: "Where the script stage usually goes wrong" },
    {
      t: "ul",
      items: [
        "**Too many scenes for the runtime.** Under fifteen seconds a scene cannot establish a place and do something in it. For a two-minute film, three to six scenes is the working range.",
        "**Rendering before reading.** The cheapest moment to fix a script is before any frame exists. A tool that goes straight from text to finished video makes every script mistake cost full price.",
        "**Prompting instead of writing.** A list of striking images is not a script. If the scenes could be shuffled without the story changing, there is no story yet.",
        "**Narration doing the work the picture should.** If the voiceover explains what we are looking at, one of the two is redundant — usually the voiceover.",
      ],
    },

    { t: "h2", text: "How MuseForge handles the script" },
    {
      t: "p",
      text: "MuseForge is a generative film maker, and it treats the script as a stage you approve rather than a box you paste into. You start from an idea — the input takes up to 2,000 characters, enough for a premise, a treatment or a scene-by-scene outline, though not a full screenplay. A Screenwriter agent drafts the title, the setting, the characters and the scenes. You review and edit that draft, and credits are only charged when you approve it. From there a Storyboard Artist plans the shots, every frame is generated from each character's locked portrait, and the scenes are animated, voiced, scored and cut.",
    },
    {
      t: "callout",
      tone: "tip",
      title: "Already have a script?",
      text: "Paste its premise and scene outline as the idea, then edit the drafted scenes in the review step until they match yours. The review step is where your script takes precedence over the model's.",
    },

    {
      t: "faq",
      items: [
        {
          q: "What is script to video AI?",
          a: "Software that turns a written script into a finished video by splitting it into scenes, producing a picture for each, adding voice and music, and exporting the result. Tools differ in what the picture is: an avatar presenter, stock footage, or generated film with a cast.",
        },
        {
          q: "Which script to video tool is best for a short film?",
          a: "A generative film maker — one that holds a cast across shots, lets you approve the script before rendering, and re-shoots a single scene. Avatar and stock-footage tools are built for explainers and social posts, not for stories with recurring characters.",
        },
        {
          q: "Can AI turn a screenplay into a movie?",
          a: "It can turn a short screenplay into a short film, scene by scene. Long screenplays are best broken into episodes or sequences, because continuity across many scenes is still the hardest part of AI video.",
        },
        {
          q: "How long should a script be for an AI video?",
          a: "Roughly one scene per 20 to 40 seconds of finished film. A two-minute film is three to six scenes; a one-minute social clip is two or three.",
        },
        {
          q: "Will the characters look the same in every scene?",
          a: "Only if the tool uses a reference image for each character on every shot. Re-describing a character in text, scene by scene, is how faces drift.",
        },
      ],
    },

    {
      t: "cta",
      title: "Write the idea, edit the script, then render",
      text: "MuseForge drafts the script from one sentence and waits for your approval before it spends a credit.",
      button: "Draft a script",
      href: "/",
    },
  ],
};

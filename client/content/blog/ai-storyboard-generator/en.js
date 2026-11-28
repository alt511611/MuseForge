export default {
  metaTitle: "AI storyboard generators: what to ask of one",
  metaDescription:
    "In AI filmmaking the storyboard is where mistakes are still cheap. What an AI storyboard generator is for, and the questions that separate a useful one.",
  title: "AI storyboard generators: what the storyboard is for, and what to ask of one",
  description:
    "In AI filmmaking the storyboard is where mistakes are still cheap. What an AI storyboard generator should do, the six things to check before trusting one, and how to storyboard a scene so the video stage has nothing left to guess.",
  blocks: [
    {
      t: "tldr",
      items: [
        "An AI storyboard generator turns a script or idea into one still frame per shot, in order, before any video is made.",
        "In AI film the storyboard matters more than in live action: a still costs a fraction of a clip and shows nearly every error a clip would.",
        "Check that it keeps characters consistent across panels, speaks in shot sizes and angles, and hands approved frames straight to video.",
        "A storyboard you cannot change one panel of is a slideshow, not a planning tool.",
      ],
    },
    {
      t: "p",
      text: "An AI storyboard generator is a tool that reads a script, a treatment or a one-line idea and produces a storyboard: one still image per shot, in story order, each with its framing decided. In live-action production a storyboard is a plan drawn before the expensive day. In AI filmmaking it is more than a plan — the storyboard frames are usually the actual first frames the video model animates. Whatever is wrong in the panel will be wrong in the film.",
    },

    { t: "h2", text: "Why the storyboard decides an AI film" },
    {
      t: "p",
      text: "Generating a still is far cheaper and faster than generating a clip, and almost every mistake an AI film makes is already visible in the still: the wrong face, a costume change, the room rearranged, an eyeline that points away from the other character, a stranger in the background. Catch those at the storyboard and each costs one image. Catch them in the edit and each costs a clip, plus every retake until it comes out right. The storyboard is the last stage where changing your mind is cheap.",
    },

    { t: "h2", text: "What to look for in an AI storyboard generator" },
    {
      t: "table",
      caption: "Six checks, most important first. The first one fails most often.",
      head: ["Check", "What good looks like"],
      rows: [
        [
          "Character consistency across panels",
          "Each character is generated from one reference portrait on every panel, not re-described in text. See [why characters drift](/blog/ai-video-character-consistency).",
        ],
        [
          "Shot vocabulary",
          "Panels are planned as wide, medium, close-up and insert, with an angle and a camera move — not as a dozen medium shots of people standing.",
        ],
        [
          "Location and light lock",
          "The same room has the same layout and the same light across every panel set in it.",
        ],
        [
          "Single-panel changes",
          "You can redo one panel, with a note, and leave the rest of the board untouched.",
        ],
        [
          "Handoff to video",
          "Approved panels become the first frames of the clips, so the video matches what you signed off.",
        ],
        [
          "Style that changes more than colour",
          "A director style should change pacing, lens and coverage, not only the grade. A filter is not a director.",
        ],
      ],
    },

    { t: "h2", text: "How to storyboard a scene" },
    {
      t: "steps",
      name: "How to storyboard a scene for an AI film",
      description:
        "A procedure for one scene, from its beats to approved panels, that leaves the video stage nothing to guess.",
      totalTime: "PT15M",
      items: [
        {
          name: "List the beats, not the lines",
          text: "Write the three to five things that happen in the scene, in order: she enters, she finds the letter, she hears the door. Each beat is a candidate shot. Dialogue lines are not beats on their own.",
        },
        {
          name: "Give each beat a shot size",
          text: "Open wide enough to say where we are, move closer as the scene tightens, and save the close-up for the beat the scene is about. If every panel is the same size, the cut will feel flat no matter how good the frames are.",
        },
        {
          name: "Fix the eyelines and the axis",
          text: "Decide where each character is looking and keep both of them on the same side of the frame across the scene. Crossing the axis by accident is the most common reason two good shots refuse to cut together.",
        },
        {
          name: "Read the panels in order, out loud",
          text: "Describe the scene from the panels alone, without the script. If you cannot tell what happened, the board is missing a beat or a shot is doing nothing.",
        },
        {
          name: "Fix single panels, then approve",
          text: "Redo only the panels that fail — a face, a costume, a stranger in frame — and approve the board. Only approved panels should go to video.",
        },
      ],
    },

    { t: "h2", text: "From storyboard to video in MuseForge" },
    {
      t: "p",
      text: "In MuseForge the storyboard is a stage of one pipeline rather than a separate tool. A Storyboard Artist agent plans each scene's shots and camera angles from the approved script. Every frame is generated from each character's locked reference portrait and the scene's locked location, so the cast and the room carry from panel to panel. The frames are then animated into the film. When a scene misses, you can retake that scene alone with a note — \"too dark\", \"show her hands\" — for one credit, and if you change a character's portrait or a location, only the scenes that use it are retaken.",
    },

    {
      t: "faq",
      items: [
        {
          q: "What is an AI storyboard generator?",
          a: "A tool that reads a script or idea and generates a storyboard — one still frame per shot, in story order, with framing decided — so a sequence can be reviewed before any video is made.",
        },
        {
          q: "Can an AI storyboard keep the same character in every panel?",
          a: "Yes, if it generates every panel from a reference portrait of that character. Tools that re-describe the character in text for each panel produce a slightly different person every time.",
        },
        {
          q: "Can I turn an AI storyboard into a video?",
          a: "In a pipeline built for it, yes: the approved panels become the first frames of each clip, and a video model animates them with the action written for each shot.",
        },
        {
          q: "How many panels does a scene need?",
          a: "One per beat, usually three to six for a scene in a short film. A scene with one panel is a still; a scene with twelve is usually covering the same beat several times.",
        },
        {
          q: "Is an AI storyboard good enough for client pitches?",
          a: "For concept approval and previsualisation, yes — a client sees the sequence, the framing and the cast before anything is budgeted. For a live-action shoot, treat it as a draft for your director of photography, not a final shot list.",
        },
      ],
    },

    {
      t: "cta",
      title: "See your idea as a storyboard",
      text: "Demo mode generates the script, the cast and the storyboard frames before you spend a credit.",
      button: "Generate a storyboard",
      href: "/",
    },
  ],
};

export default {
  title: "How to write a text-to-video prompt that produces the shot you pictured",
  description:
    "Video prompts are not image prompts with a verb added. A shot has a camera, a subject, an action, a light and a duration — and the order you state them in changes what you get.",
  blocks: [
    {
      t: "tldr",
      items: [
        "A video prompt describes **a shot**, not a picture: framing, subject, action, lighting, lens, mood — roughly in that order.",
        "Put the framing first. It is the clause the model is most likely to honour, and the one that most changes the result.",
        "One action per shot. Two verbs in one prompt produce a clip that does neither properly.",
        "Describe what is in frame, never what is absent — negation is the least reliable instruction you can give.",
        "Keep the fixed clauses byte-identical across a scene's shots so lighting and wardrobe do not drift.",
      ],
    },
    {
      t: "p",
      text: "Most bad AI video comes from a prompt that would have made a perfectly good image. \"A woman in a kitchen, cinematic, 4k, beautiful lighting\" describes a photograph. A shot also has to say where the camera is, what happens, and for how long — and when you leave those out, the model picks, and it picks the most average option available.",
    },

    { t: "h2", text: "The six clauses of a shot" },
    {
      t: "p",
      text: "A reliable prompt has the same skeleton every time. Fill the six slots and the model has nothing important left to guess.",
    },
    {
      t: "keyfacts",
      items: [
        { term: "1. Framing", value: "Wide, medium, close-up, over-the-shoulder — and where the subject sits in frame. State this first." },
        { term: "2. Subject", value: "Who, wearing what. Identical wording in every shot of the scene." },
        { term: "3. Action", value: "One verb. What changes between the first frame and the last." },
        { term: "4. Camera", value: "Static, slow push in, handheld, pan left. \"Cinematic\" is not a camera move." },
        { term: "5. Light", value: "Source, direction, quality — \"low window light from the left, soft\". This is the clause that makes it look shot rather than rendered." },
        { term: "6. Mood / grade", value: "The tonal treatment. Last, because it is the one the model may safely reinterpret." },
      ],
    },
    {
      t: "p",
      text: "Written out, that is: *\"Medium shot, a woman in a charcoal wool coat standing at a kitchen counter, she sets down a mug and looks toward the door, camera static, low window light from the left, soft, muted cool grade.\"* It is not poetic. It is unambiguous, which is the only quality a prompt needs.",
    },

    { t: "h2", text: "Rules that change the output most" },
    {
      t: "h3", text: "One action per shot",
    },
    {
      t: "p",
      text: "\"She walks in, takes off her coat and sits down\" gives you three seconds in which all three things half-happen. Video models allocate the clip's duration across whatever you asked for. Ask for one thing and it gets the whole clip.",
    },
    { t: "h3", text: "Never describe absence" },
    {
      t: "p",
      text: "\"No other people in the room\" reliably puts other people in the room. The prompt is a description of what to draw, and every noun in it is a candidate to appear. Describe the empty room affirmatively instead: \"an empty kitchen, one chair pushed back.\"",
    },
    { t: "h3", text: "Say where the eyes go" },
    {
      t: "p",
      text: "Unless told otherwise, generated actors look at the lens. In a drama that is wrong in every shot. Add an eyeline to every prompt — \"looking off-frame left, at someone out of shot\" — and the footage starts reading as a scene rather than as a portrait that moves.",
    },
    { t: "h3", text: "Repeat the fixed clauses exactly" },
    {
      t: "p",
      text: "Within one scene, the subject clause, the light clause and the grade clause should be copied character-for-character between shots. Rewording \"low window light from the left\" as \"soft morning light\" in shot three is enough to move the sun. The clauses that vary between shots should be framing and action, and nothing else.",
    },
    {
      t: "callout",
      tone: "tip",
      title: "Quality words are mostly decoration",
      text: "\"4k\", \"masterpiece\", \"award-winning\", \"highly detailed\" do very little in current video models and crowd out clauses that do. A specific lens and a specific light beat a stack of quality adjectives every time.",
    },

    { t: "h2", text: "Before and after" },
    {
      t: "table",
      caption: "The same intended shot, prompted vaguely and prompted as a shot.",
      head: ["Vague", "Specific", "What changes"],
      rows: [
        ["A detective in an office, cinematic", "Medium shot, a detective in a grey coat at a desk, she turns a photograph face down, camera static, hard desk lamp from the right, noir grade", "Framing, action and light are decided by you rather than sampled"],
        ["She reacts, dramatic", "Close-up, her face, she stops mid-breath and looks off-frame left, camera slowly pushes in, same desk lamp from the right", "A readable beat instead of an unspecified emotion"],
        ["Beautiful establishing shot of the city", "Wide shot, rain-wet street at night from across the road, neon sign reflecting in a puddle, camera static, practical light only", "A place with geography instead of a stock postcard"],
      ],
    },

    { t: "h2", text: "Aspect ratio is part of the prompt" },
    {
      t: "p",
      text: "A shot composed for 16:9 does not survive a crop to 9:16 — the crop takes the middle of the frame, and in a well-composed wide the middle is usually empty space between two people. Decide the delivery ratio before you generate, and compose for it. If you need both, generate for the wider one and crop with the subject's position in mind rather than the frame's centre.",
    },

    { t: "h2", text: "Where prompts stop being the answer" },
    {
      t: "p",
      text: "There is a ceiling on what prompting alone can do, and it is exactly where consistency begins. No amount of clause discipline will make shot six's face match shot one's, because that is not a prompting problem — it is a state problem, and the fix is a reference image rather than better words. That is covered separately in [why AI characters drift](/blog/ai-video-character-consistency).",
    },
    {
      t: "p",
      text: "This is also the part a pipeline can take off your hands. MuseForge assembles each frame prompt from the scene's own locks — the cast sheet, the lighting, the director preset — so the clauses that must not vary are not retyped per shot and therefore cannot drift.",
    },

    {
      t: "faq",
      items: [
        {
          q: "How long should a text-to-video prompt be?",
          a: "Long enough to fill the six slots — framing, subject, action, camera, light, mood — and no longer. In practice one to three sentences. Prompts past roughly sixty words tend to have their later clauses ignored, so spend the budget on specifics rather than adjectives.",
        },
        {
          q: "Do negative prompts work in video models?",
          a: "Some tools accept a separate negative prompt field and it has modest effect there. Negation written inside the main prompt — \"no cars, not smiling\" — works poorly and often produces the thing you excluded. Describe the scene you want affirmatively instead.",
        },
        {
          q: "Why does everyone in my AI video look at the camera?",
          a: "Because that is the default for a subject in a generated frame, and nothing in a typical prompt contradicts it. Add an explicit eyeline to every shot — who or what the character is looking at, and which side of frame it is on.",
        },
        {
          q: "Should I put the camera movement at the start or end of the prompt?",
          a: "After the action and before the lighting. Framing belongs at the very front because it is honoured most strongly; camera movement in the middle is reliably picked up without displacing the subject description.",
        },
        {
          q: "Does adding '4k' or 'cinematic' improve AI video quality?",
          a: "Barely, and they cost you prompt space. A named lens, a named light source and a named grade change the image far more than generic quality words do.",
        },
        {
          q: "Why does my character's clothing change between shots?",
          a: "Because the wardrobe clause was reworded. A reference image holds the face far more strongly than it holds clothing, so the garment has to be restated in every shot of the scene using identical wording.",
        },
      ],
    },

    {
      t: "cta",
      title: "Let the pipeline write the clauses",
      text: "MuseForge builds every frame prompt from the scene's locked cast, lighting and director preset — so the parts that must stay identical, do.",
      button: "See it run",
      href: "/",
    },
  ],
};

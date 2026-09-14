const title = "Why AI video characters change between shots — and how to lock them";

export default {
  title,
  description:
    "A face that drifts between scene 2 and scene 3 is the single most common reason an AI short film looks fake. Here is what causes the drift, and the four techniques that actually stop it.",
  blocks: [
    {
      t: "tldr",
      items: [
        "Characters drift because most text-to-video tools generate each shot from the prompt alone — nothing carries the face from one shot to the next.",
        "Re-describing the person in words (\"brown hair, green eyes, 30s\") does not fix it: two runs of the same description produce two different people.",
        "The fix is a **reference image**, generated once and fed into every later shot as an image input, not a text one.",
        "Lock the wardrobe, the lighting and the lens along with the face, or the character stays recognisable while the world around them does not.",
      ],
    },
    {
      t: "p",
      text: "You write a three-scene story. Scene one looks great. Scene two, the protagonist's nose is different. Scene three she has gained a jacket nobody asked for and the kitchen has moved to a different apartment. This is the defining failure mode of AI video, and it has a specific cause.",
    },

    { t: "h2", text: "Why the drift happens" },
    {
      t: "p",
      text: "A text-to-video model is a sampler. Give it the prompt *\"a woman in her thirties, brown hair, standing in a kitchen\"* and it returns one plausible sample from an enormous space of women in their thirties with brown hair in kitchens. Run it again and you get a different sample. The model is not being inconsistent — you asked twice and it answered twice, correctly both times.",
    },
    {
      t: "p",
      text: "Nothing in that loop carries state. The second shot does not know the first shot happened. This is why the problem gets worse the longer your film is: drift compounds, and by shot six there is no visual relationship left to the character you started with.",
    },
    {
      t: "keyfacts",
      items: [
        { term: "Root cause", value: "Each shot is sampled independently from text; no visual state is carried between them." },
        { term: "Doesn't fix it", value: "More adjectives, longer descriptions, naming the character, raising the seed count." },
        { term: "Does fix it", value: "One reference image reused as an image input on every subsequent shot." },
        { term: "Also drifts", value: "Wardrobe, hairstyle, room, time of day, lens and colour grade — each needs its own lock." },
        { term: "Compounding", value: "Drift accumulates per shot, so a 6-shot film degrades far more than a 2-shot one." },
      ],
    },

    { t: "h2", text: "What does not work" },
    {
      t: "p",
      text: "Before the techniques that work, it is worth being precise about the ones that do not, because all of them are widely recommended.",
    },
    {
      t: "ul",
      items: [
        "**Longer descriptions.** Going from \"a woman\" to \"a 34-year-old woman with shoulder-length chestnut hair, a small scar above her left eyebrow, hazel eyes\" narrows the space. It does not collapse it. You will get a different person who matches all of those words.",
        "**Naming the character.** \"Sarah walks into the room\" gives the model nothing. It does not know who Sarah is, and there is no Sarah in its weights.",
        "**Fixing the seed.** A fixed seed reproduces the same output for the *same prompt*. Your shots have different prompts by definition — different action, different framing — so the seed no longer pins the face.",
        "**Generating one long take.** This does hold the character, but it costs you every cut, and a film without cuts is not a film. It is a clip.",
      ],
    },

    { t: "h2", text: "The four locks" },
    {
      t: "p",
      text: "Consistency is not one problem, it is four, and a film that solves only the first still looks wrong. Solve them in this order.",
    },
    {
      t: "steps",
      name: "How to lock a character across every shot of an AI video",
      description:
        "Four passes that together keep a character, their wardrobe, their world and the camera identical from the first shot to the last.",
      totalTime: "PT20M",
      items: [
        {
          name: "Generate the portrait once, before any shot",
          text: "Produce a single clean reference image of the character — neutral expression, even lighting, front three-quarter angle. Do not generate it as part of a scene. A portrait extracted from a dramatic shot carries that shot's lighting and mood into every future frame that references it.",
        },
        {
          name: "Feed the portrait as an image input, not a description",
          text: "Every subsequent shot must receive the portrait itself through an image-to-image or reference-image input. This is the actual lock: the model is now conditioned on pixels rather than on adjectives, and pixels do not resample.",
        },
        {
          name: "Write the wardrobe and hair into the locked description too",
          text: "The reference image holds the face. It does not reliably hold a jacket. State the wardrobe explicitly in every shot prompt and keep the wording byte-identical between shots — \"charcoal wool coat, collar up\" in all six, not \"grey coat\" in one of them.",
        },
        {
          name: "Lock the world: light, lens and grade",
          text: "Repeat the lighting direction, the lens and the colour treatment in every prompt of a scene. A character who is recognisable while the room's light jumps from morning to dusk between cuts reads as a continuity error, not as a consistent character.",
        },
      ],
    },
    {
      t: "callout",
      tone: "tip",
      title: "Why the portrait must be boring",
      text: "A reference portrait shot dramatically — hard side light, extreme angle, shadow across half the face — gives the model less information about the face, not more. Half of it is hidden. Even, frontal, unremarkable lighting is the most informative portrait you can make.",
    },

    { t: "h2", text: "Doing it by hand versus having it enforced" },
    {
      t: "p",
      text: "Every technique above is something you can do manually in any tool that accepts an image input: generate the portrait, save it, attach it to each shot, and copy-paste the wardrobe clause into each prompt. It works. It is also four opportunities per shot to make a mistake, and the mistake is only visible after you have paid for the render.",
    },
    {
      t: "p",
      text: "The alternative is a pipeline where the locks are structural rather than procedural. [MuseForge](/) generates the character portrait once at the start of a run and reuses it on every frame of every scene automatically, carries the wardrobe and lighting clauses through the whole shot list, and keeps the same locks when you order a second episode — so episode two's protagonist is the same person as episode one's without you re-supplying anything.",
    },
    {
      t: "table",
      caption: "The same four locks, applied manually versus enforced by the pipeline.",
      head: ["Lock", "By hand", "Enforced"],
      rows: [
        ["Face", "Save a portrait, attach it to each shot", "Generated once, attached automatically to every frame"],
        ["Wardrobe", "Copy the clause into each prompt", "Carried through the shot list from the cast sheet"],
        ["Lighting / lens", "Restate per shot, hope for consistency", "Held per scene as a production lock"],
        ["Across episodes", "Re-supply everything, from memory", "The cast and locks travel with the series"],
      ],
    },

    { t: "h2", text: "When a character has to change on purpose" },
    {
      t: "p",
      text: "Locking is only useful if you can also break the lock deliberately. A character who puts on a red coat in scene four needs the coat to persist from that point forward — not to flicker back off in scene five, and not to appear retroactively in scene one.",
    },
    {
      t: "p",
      text: "The clean way to do this is to edit the locked reference itself and re-render only the shots downstream of the change, rather than re-prompting every shot and hoping. Re-rendering the whole film to change one garment is how a budget disappears.",
    },

    {
      t: "faq",
      items: [
        {
          q: "Why do AI video characters change between scenes?",
          a: "Because each shot is generated independently from its text prompt, and nothing carries the character's appearance from one shot to the next. The model samples a new plausible person every time. Only conditioning later shots on an actual reference image of the character stops it.",
        },
        {
          q: "Does a more detailed character description fix consistency?",
          a: "No. A longer description narrows the range of faces the model can return but never narrows it to one. Two generations from the same detailed description reliably produce two different people who both match the description.",
        },
        {
          q: "Can a fixed seed keep an AI character consistent?",
          a: "Not across a film. A seed reproduces the same output only for an identical prompt. Because every shot in a story has a different prompt — different action, framing and dialogue — the seed stops pinning the character as soon as the prompt changes.",
        },
        {
          q: "How many reference images do I need per character?",
          a: "One good one, used everywhere, beats several inconsistent ones. A single evenly lit front three-quarter portrait is enough for most pipelines; adding a second reference shot in different lighting tends to widen the range the model draws from rather than narrowing it.",
        },
        {
          q: "Does character consistency also cover clothing and hair?",
          a: "Only partially. A reference portrait holds facial structure strongly and hairstyle moderately; it holds clothing weakly, especially below the shoulders. Wardrobe needs to be restated in the prompt of every shot, using identical wording each time.",
        },
        {
          q: "What about consistency across episodes, not just scenes?",
          a: "It is the same problem one level up, and it needs the same answer: the reference portrait and the production locks have to be stored with the series and reapplied to the next episode. A tool that discards them at the end of a render will give you a new lead actor in episode two.",
        },
      ],
    },

    {
      t: "cta",
      title: "See the lock working",
      text: "Demo mode runs the whole pipeline — cast portrait, storyboard, frames — without an API key and without spending a credit.",
      button: "Try MuseForge free",
      href: "/",
    },
  ],
};

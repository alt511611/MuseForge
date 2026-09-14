export default {
  title: "The micro-drama playbook: shipping a series instead of a one-off",
  description:
    "Vertical micro-dramas are built on retention across episodes, not production value inside one. What the format actually requires, and why episode two is the one that decides whether you have a series.",
  blocks: [
    {
      t: "tldr",
      items: [
        "A micro-drama is a serialised vertical drama in 1–3 minute episodes, built to be watched in a feed.",
        "The format's economics come from **serialisation**: the second episode costs a fraction of the first and keeps most of its audience.",
        "The hard requirement is continuity — same faces, same world, episode after episode. This is what makes AI production viable or impossible.",
        "Structure every episode to end on an unanswered question, then start the next one from that question rather than from a new premise.",
      ],
    },
    {
      t: "p",
      text: "The micro-drama is the one video format that AI production is genuinely well suited to, and it is worth being clear about why. It is not that the format is undemanding — it is that its demands are structural rather than spectacular. A micro-drama does not need a crane shot. It needs the same woman in the same apartment, forty episodes running.",
    },

    { t: "h2", text: "What the format actually is" },
    {
      t: "keyfacts",
      items: [
        { term: "Episode length", value: "60–180 seconds. Short enough to finish on a scroll, long enough to turn once." },
        { term: "Orientation", value: "Vertical 9:16, composed for it rather than cropped into it." },
        { term: "Season length", value: "Typically 20–100 episodes. The format assumes bingeing, not appointment viewing." },
        { term: "Structure", value: "One turn per episode, ending on an open question." },
        { term: "Production constraint", value: "Cast, wardrobe and locations must survive across the whole run." },
        { term: "What kills a series", value: "Not a weak pilot — an inconsistent second episode." },
      ],
    },

    { t: "h2", text: "Why episode two is the whole business" },
    {
      t: "p",
      text: "Anyone can make one good short. The reason most AI-made series die is that the second episode is produced from scratch: a new run, a new prompt, and therefore a new lead actor who resembles the first one about as much as a cousin does. The audience does not articulate this. They just stop watching.",
    },
    {
      t: "p",
      text: "Serialisation is the only thing that makes the numbers work. The first episode carries the cost of inventing the world — cast, tone, locations, look. Every episode after it inherits all of that, which means the marginal cost of episode twelve is a fraction of episode one's, while its audience retention is far higher because the viewer already knows who these people are.",
    },
    {
      t: "callout",
      tone: "note",
      title: "The state a series has to carry",
      text: "Four things must survive between episodes: the locked cast portraits, the production locks (lighting, lens, grade), the story so far, and the question the last episode's final frame left open. A tool that discards these at the end of a render is a tool for making pilots, not series.",
    },

    { t: "h2", text: "Structuring an episode" },
    {
      t: "steps",
      name: "How to structure a micro-drama episode",
      description: "The four-beat shape that fits 60–180 seconds and hands off cleanly to the next episode.",
      totalTime: "PT15M",
      items: [
        {
          name: "Open inside the situation",
          text: "No establishing, no preamble. The first three seconds decide whether the episode is watched at all, and in a feed they compete with everything else. Start on the line that is already mid-argument.",
        },
        {
          name: "Give one new fact",
          text: "An episode delivers exactly one new piece of information — a revelation, a betrayal, an arrival. Two makes the episode feel rushed; zero makes it filler, and filler in a feed is unsubscribed from immediately.",
        },
        {
          name: "Turn on that fact",
          text: "Something about the situation must be different at the end than at the start because of the new fact. This is the beat the episode exists for.",
        },
        {
          name: "End on the question, not the answer",
          text: "The final frame should raise something the next episode has to resolve. Practically: cut one beat earlier than feels comfortable. The next episode then has its premise handed to it — you do not need a new idea to order it.",
        },
      ],
    },

    { t: "h2", text: "Vertical is a composition, not a crop" },
    {
      t: "p",
      text: "A 16:9 shot cropped to 9:16 takes the centre of the frame, and in a two-person scene the centre of the frame is the gap between them. Compose vertically from the start: single subjects, tight framing, faces in the upper third where the thumb is not covering them.",
    },
    {
      t: "p",
      text: "When you do need to reframe existing footage, crop toward the subject rather than the frame centre, and respect the scene's 180° axis so the characters do not swap sides across a cut. MuseForge does this automatically — vertical exports are pointed at the face using the axis the film's own frame prompts locked, rather than at the geometric middle.",
    },

    { t: "h2", text: "A realistic production loop" },
    {
      t: "ol",
      items: [
        "**Pilot.** Establish cast, world and tone. Spend disproportionate effort here — everything downstream inherits it.",
        "**Lock.** Save the cast portraits and production locks as the series' state, not as one render's leftovers.",
        "**Episode run.** Order the next episode from the open question. No new premise required.",
        "**Retake, don't re-render.** When one shot is wrong, re-shoot that beat. Re-running the episode to fix one framing is how a series stops being economical.",
        "**Re-cut.** Reorder and trim from clips you already paid for. A tighter cut of existing footage costs nothing and is usually the biggest available quality gain.",
      ],
    },

    {
      t: "faq",
      items: [
        {
          q: "What is a micro-drama?",
          a: "A serialised vertical drama told in episodes of roughly one to three minutes, designed for feed-based viewing. Seasons typically run from twenty to a hundred episodes, and each episode delivers one turn and ends on an open question.",
        },
        {
          q: "How long should a micro-drama episode be?",
          a: "Sixty to a hundred and eighty seconds. Under sixty there is no room to turn the situation; over three minutes the format's core assumption — that the viewer finishes the episode in one scroll — stops holding.",
        },
        {
          q: "Can AI realistically produce a micro-drama series?",
          a: "Yes, and better than it produces one-off films, because the format's hardest requirement is continuity rather than spectacle. The decisive question is whether your tool carries the cast and the production locks from one episode to the next, or regenerates them each time.",
        },
        {
          q: "Why do AI-made series fail at episode two?",
          a: "Because the second episode is usually generated as a fresh run, so the lead character's face, wardrobe and world all resample. Viewers read this as a different show and leave. The fix is storing the reference portraits and locks with the series and reapplying them.",
        },
        {
          q: "Should I write the whole season before producing episode one?",
          a: "Write the shape of the season — the arc and roughly where the turns fall — and the first three episodes in full. Writing all forty in advance wastes the information the first three episodes' retention data gives you.",
        },
        {
          q: "Does a micro-drama need to be shot vertically from the start?",
          a: "It should be composed vertically from the start. Cropping 16:9 footage to 9:16 takes the middle of the frame, which in most well-composed shots is the least interesting part of it.",
        },
      ],
    },

    {
      t: "cta",
      title: "Order episode two without a new idea",
      text: "MuseForge carries the cast, the locks and the open question forward, so the next episode is a sequel rather than a second pilot.",
      button: "Start a series",
      href: "/",
    },
  ],
};

/*
 * The questions people put to a tool like this in AI-video communities
 * (r/aivideo and neighbours) are practical and a little suspicious: what does
 * a film really cost, does the face hold, what happens when a shot is wrong,
 * what can't it do. They are answered here directly, limits included, because
 * a forum thread that says "it doesn't do X" gets quoted and an evasive
 * product page does not.
 *
 * NOTE ON PROVENANCE. The question list was NOT scraped from Reddit: the
 * research tooling could not read reddit.com on 2026-11-28. It comes from
 * what those communities are known to ask plus OpenSEO's "people also ask"
 * data. Replace or extend it with real threads when someone pastes them.
 *
 * Every fact below is read from the product's own strings (locales/en.js) or
 * the pricing page: credits, retakes at 1 credit, free trims, 30-day credit
 * expiry, lip sync only when one visible character speaks, optional photo,
 * Whop as merchant of record. Model vendors and data-training policy are
 * deliberately NOT stated: neither is declared anywhere public, and a guess
 * in an FAQ is a promise.
 */
export default {
  title: "MuseForge questions: credits, retakes, lip sync, consistency and limits",
  metaTitle: "MuseForge FAQ: credits, retakes, lip sync, limits",
  description:
    "Straight answers about MuseForge: what a film costs in credits, what a retake costs, whether faces stay consistent, how lip sync works, what the free plan includes, and what it cannot do.",
  metaDescription:
    "What a MuseForge film costs in credits, what a retake costs, how character consistency and lip sync work, what Free includes, and what it cannot do.",
  blocks: [
    {
      t: "tldr",
      items: [
        "MuseForge turns one idea into a finished short film: script, cast, storyboard, video, voices, music and edit. One credit is about ten seconds of finished film.",
        "You approve the script before any credit is charged. A retake of one scene costs 1 credit; reordering, trimming or dropping scenes is free.",
        "Faces stay consistent because every frame is generated from one locked reference portrait per character. It can still miss, and a retake fixes it.",
        "Free includes 3 real credits a month and is watermarked. Creator and Pro remove the watermark.",
      ],
    },

    { t: "h2", text: "Cost and plans" },
    {
      t: "faq",
      items: [
        {
          q: "How much does a MuseForge film cost?",
          a: "Cost is in credits, and one credit is about ten seconds of finished film. The Free plan includes 3 real credits a month, Creator (from $53 a month) includes 16 and Pro (from $116 a month) includes 36. Background music adds 1 credit and lip sync adds 1 credit per scene; the estimate screen shows the total before you spend anything. Credit packs are available without a subscription.",
        },
        {
          q: "Do I pay before I see the script?",
          a: "No. The script is written and shown to you first, and credits are charged only when you approve it. You can edit the script before approving. Demo mode goes further and runs the pipeline with placeholder visuals so you can test an idea without credits.",
        },
        {
          q: "What does a retake cost?",
          a: "Retaking one scene costs 1 credit, and you can say what should change, such as \"too dark\" or \"show her hands\". Changing the locked portrait or location retakes every affected scene at 1 credit per scene. Reordering, trimming or dropping scenes does not regenerate anything and is free.",
        },
        {
          q: "Do credits expire?",
          a: "Yes. Every credit, whether it comes with your plan or from a credit pack, is usable immediately and expires 30 days after it is added. Unused credits do not roll over.",
        },
        {
          q: "Can I cancel any time?",
          a: "Yes. Cancellation takes effect at the next billing date. Payments are processed by Whop, the merchant of record, with Visa, Mastercard and most major cards.",
        },
      ],
    },

    { t: "h2", text: "Quality and consistency" },
    {
      t: "faq",
      items: [
        {
          q: "Does the character really look the same in every scene?",
          a: "Mostly, by design: each character has one reference portrait, generated for you or uploaded, and every frame is generated from it, with wardrobe and lighting locked across the shot list. No current AI film tool guarantees an identical face in every shot, so check the finished scenes and retake any that drifted for 1 credit each.",
        },
        {
          q: "Do I have to upload a photo of a character?",
          a: "No. Uploading is optional. If you skip it, the AI generates a consistent reference portrait. You can upload your own photo at any time, and you can upload a location photo too.",
        },
        {
          q: "How does lip sync work, and when does it not?",
          a: "Dialogue is voiced per character. Lip sync is applied only when one visible character speaks in a shot where the mouth is readable; otherwise the dialogue stays a clean voice-over. In some languages the video model speaks natively and lip sync is included. Lip sync is optional and costs 1 credit per scene.",
        },
        {
          q: "Can it make a series with the same cast?",
          a: "Yes, on the Pro plan. A series keeps the cast, the setting and the story so far, so each new episode continues the last instead of starting over.",
        },
      ],
    },

    { t: "h2", text: "Output, rights and limits" },
    {
      t: "faq",
      items: [
        {
          q: "How long can a film be?",
          a: "A single run is limited by scenes: up to 8 on Free, 16 on Creator (about 3 minutes) and 24 on Pro (about 4 minutes). A longer film is assembled from several runs.",
        },
        {
          q: "Can I make vertical video for TikTok or Reels?",
          a: "Yes. Every film has a 9:16 download for TikTok, Reels and Shorts, and the Creator and Pro plans include all aspect ratios, so you can also choose the format before generating a series.",
        },
        {
          q: "Is the free plan watermarked?",
          a: "Yes. Free films are watermarked and in standard quality. Creator and Pro have no watermark, and Pro adds HD export.",
        },
        {
          q: "Can I use what I make commercially?",
          a: "Yes. All videos are licensed to you for personal and commercial use, on every plan including Free.",
        },
        {
          q: "What can't MuseForge do?",
          a: "It is not a frame-by-frame editor: you can edit the script, the cut and single scenes, but not paint every frame. It does not make a feature-length film in one run, since Pro reaches about four minutes. And because the models can miss, plan for the occasional retake.",
        },
      ],
    },

    {
      t: "cta",
      title: "Try it before you spend a credit",
      text: "Demo mode runs the whole pipeline with placeholder visuals, free.",
      button: "Start with an idea",
      href: "/",
    },
  ],
};

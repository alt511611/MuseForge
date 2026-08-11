/**
 * The site's example reels — the single source of truth.
 *
 * The whole landing page and every /solutions page pull their video from this
 * list, so the site never asks for more footage than there is. Three reels is
 * the budget: one hero, one landscape example, one vertical example.
 *
 * To publish a reel, drop the files in `client/public/examples/` and fill in
 * `src` (+ `poster`). Until then the slot renders as an empty graded frame
 * labelled as pending — it never shows a stand-in that pretends to be output.
 *
 * See `client/public/examples/README.md` for the prompt behind each reel and
 * the exact settings to reproduce it.
 */
export const REELS = [
  {
    id: "neon-harbour",
    title: "Neon Harbour",
    /* Technical metadata only — reads the same in every locale, so it needs
       no translation key. */
    meta: "Sci-Fi · 16:9 · Cinematic Balanced",
    aspect: "16/9",
    src: null, // "/examples/neon-harbour.mp4"
    poster: null, // "/examples/neon-harbour.jpg"
    /* Shown on the page as the prompt that produced the reel. */
    prompt:
      "A dock worker on a rain-soaked cargo harbour finds a shipping container " +
      "that hums with light, and the city's power dies the moment she opens it.",
    tone: "linear-gradient(160deg,#1e3a8a 0%,#6d28d9 58%,#07070b 100%)",
    accent: "#60a5fa",
  },
  {
    id: "the-last-letter",
    title: "The Last Letter",
    meta: "Romance · 16:9 · Warm Nostalgia",
    aspect: "16/9",
    src: null,
    poster: null,
    prompt:
      "An old bookseller finds a love letter she wrote at nineteen tucked inside " +
      "a returned novel, and walks to the address on the envelope one last time.",
    tone: "linear-gradient(160deg,#7c2d12 0%,#e8b64c 58%,#07070b 100%)",
    accent: "#f3d38a",
  },
  {
    id: "the-tell",
    title: "The Tell",
    meta: "Noir · 9:16 · Noir Mystery",
    aspect: "9/16",
    src: null,
    poster: null,
    prompt:
      "A card dealer in a basement game realises the man across the table is " +
      "copying her own tell, move for move, and only one of them knows why.",
    tone: "linear-gradient(160deg,#27272a 0%,#4c1d95 60%,#07070b 100%)",
    accent: "#c084fc",
  },
];

/** The hero reel — the one frame the page opens on. */
export const HERO_REEL = REELS[0];

/** The two examples shown side by side in the showcase section. */
export const SHOWCASE_REELS = [REELS[1], REELS[2]];

/** Solution pages each embed one reel; pick a stable one per segment so the
    four pages don't all open on the same clip. */
export function reelForSegment(segment) {
  const bySegment = {
    agencies: "neon-harbour",
    creators: "the-tell",
    filmmakers: "the-last-letter",
    education: "neon-harbour",
  };
  return REELS.find((r) => r.id === bySegment[segment]) || REELS[0];
}

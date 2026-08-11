# Example reels

The whole site runs on **three** clips. The landing page hero shows one, the
showcase section shows the other two, and each `/solutions/*` page re-embeds
one of the three. There is deliberately nowhere else that asks for footage.

To publish a reel, drop the files here and fill in `src` / `poster` in
[`client/lib/showcase.js`](../../lib/showcase.js). A reel with `src: null`
renders as a graded frame labelled "Rendering" — the layout holds, and nothing
pretends to be output that does not exist yet.

## File naming

| Reel | Video | Poster |
| --- | --- | --- |
| Neon Harbour | `neon-harbour.mp4` | `neon-harbour.jpg` |
| The Last Letter | `the-last-letter.mp4` | `the-last-letter.jpg` |
| The Tell | `the-tell.mp4` | `the-tell.jpg` |

Keep each clip **under ~6 MB** (H.264, ~2 Mbps, no audio track needed unless the
sound is worth unmuting for) — all three can be on screen in one session and
they are served straight from `public/`. The poster is a still from the clip at
the same aspect ratio; without one the frame is empty until the video decodes.

## The prompts to generate them

Run these through MuseForge itself. The settings matter as much as the idea —
the site claims a specific preset and aspect ratio next to each clip.

### 1. Neon Harbour — hero, 16:9

- **Style:** Sci-Fi · **Director preset:** Cinematic Balanced · **Aspect:** 16:9
- **Scenes:** 3

> A dock worker on a rain-soaked cargo harbour finds a shipping container that
> hums with light, and the city's power dies the moment she opens it. Open wide
> on the harbour at night with sodium lamps in the rain, push in as she cuts the
> seal, and end on her face lit only by whatever is inside as the skyline behind
> her goes black.

### 2. The Last Letter — showcase, 16:9

- **Style:** Romance · **Director preset:** Warm Nostalgia · **Aspect:** 16:9
- **Scenes:** 3

> An old bookseller finds a love letter she wrote at nineteen tucked inside a
> returned novel, and walks to the address on the envelope one last time. Start
> close on her hands and the folded paper in a quiet shop at golden hour, cut to
> her walking a street she clearly knows by heart, and hold on the door she does
> not knock on.

### 3. The Tell — showcase, 9:16

- **Style:** Noir · **Director preset:** Noir Mystery · **Aspect:** 9:16
- **Scenes:** 3

> A card dealer in a basement game realises the man across the table is copying
> her own tell, move for move, and only one of them knows why. Keep it tight and
> vertical: her eyes, his hands, the chips — hard key light from a single lamp
> above the table, everything else falling into black.

Shoot the vertical one vertical. The whole point of the third slot is proving
the 9:16 output is real, so a cropped 16:9 render defeats it.

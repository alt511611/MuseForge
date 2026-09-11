# MuseForge

**Agentic AI video studio** — one text idea becomes a finished cinematic
micro-drama: written, shot, cut, scored, mixed and subtitled.

```
Idea → Screenwriter → Storyboard Artist → Opening Frame → Scene Take → Finish
        (Claude)        (Claude)           (image model)   (video model)  (mix, grade, captions)
```

## What makes it different

Most tools in this category generate **clips**. MuseForge delivers a
**finished cut**, and almost everything below follows from that one
difference.

### 1. The price is a number you know before you spend it

One credit buys `SECONDS_PER_CREDIT` seconds of finished film — ten, today —
and the whole drama's length is fixed *before* a single credit is charged
(`interfaces/second_budget`). Dramatic tension still decides how those seconds
are *distributed* between scenes; it can no longer change the total.

Credit systems elsewhere burn by model, resolution and second, so what a
customer is buying is only knowable after they have bought it.

### 2. The audio is delivered, not just generated

The part of AI video that most reliably gives the game away is the sound. This
pipeline finishes it:

| | |
|---|---|
| Loudness | EBU R128, `I=-14 LUFS`, `TP=-1.5 dBTP` — the streaming delivery spec |
| Dialogue | Sidechain-ducked score (`threshold 0.045`, `ratio 8`, `15ms` attack, `320ms` release) |
| Score | Rides the script's own tension curve rather than sitting at one level (`interfaces/score`) |
| Foley | One bed per scene, from the sound note the storyboard has always written |
| Subtitles | Broadcast typesetting: 42 characters × 2 lines, 17 chars/sec, no speaker labels, and a cue never outlives the shot that says it (`interfaces/subtitles`) |

### 3. Changing your mind is cheap

| Action | Cost |
|---|---|
| Re-cut the timeline (reorder, trim, drop scenes) | **Free** — it reuses clips already paid for |
| Retake one scene | 1 credit |
| Change a costume or a location *everywhere* | 1 credit per affected scene |
| Restore an earlier take | Free |
| Approve or edit the script before shooting | Free — credits are charged *after* this gate |

### And the things everyone needs to get right

- **Character lock.** One portrait per character (optionally a four-view
  reference sheet), reused in every scene, carried into the take as an
  *element* — with the wardrobe restated as text, because a reference image
  binds a face and never an outfit.
- **A scene is one take.** On a backend that can cut inside a single
  generation, a scene's framings are beats of one request instead of N
  separate generations (`interfaces/scene_take`). Extra cuts then cost
  nothing, which is why a 30-second drama is no longer limited to six shots.
- **Vertical that keeps the subject.** 9:16 and 1:1 exports place the crop
  window per shot from a measurement of the picture, rather than taking the
  middle and hoping (`interfaces/reframe`).
- **One place per endpoint.** Every video endpoint declares what it accepts,
  how long it can run, how many references it reads, whether it speaks and in
  which languages, and whether it can cut inside a generation
  (`interfaces/video_backend`). Everything else reads that declaration.
- **Demo mode.** The whole pipeline runs with no API key at all.

## Providers

Video, image, voice, music, SFX and lip sync are each selected independently.
MuAPI covers all of them, which is the zero-configuration path; fal.ai and
ElevenLabs are alternatives for the stages where they are currently better or
cheaper, and a local GPU can serve lip sync. See the configuration map at the
top of `.env.example` — it separates the handful of keys you must set from the
tuned defaults you should leave alone.

## Quick start

### Demo mode (zero config)

```bash
cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python api.py
```

```bash
cd client && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and generate a drama — no
API keys needed.

### With real generation

```bash
cp .env.example server/.env
```

Set `MUAPI_KEY` (and optionally `ANTHROPIC_API_KEY`); read the configuration
map at the top of the file before changing anything else.

### Docker (full stack)

```bash
docker compose up --build
```

### Tests

```bash
cd server && .venv/bin/python -m pytest -q
```

The suite runs fully offline and is larger than the product it tests — which
is what selling a delivery guarantee costs in engineering.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health + demo/keys status |
| GET | `/api/director-styles` | List director presets |
| POST | `/api/estimate` | Render time / asset estimate |
| POST | `/api/generate` | Start a generation job |
| GET | `/api/jobs/{id}` | Job status + result |
| GET | `/api/jobs/{id}/stream` | SSE progress stream (with heartbeat) |
| GET | `/api/jobs/{id}/video` | Stream/download the final video |
| POST | `/api/jobs/{id}/cancel` | Cancel a running job |
| POST | `/api/jobs/{id}/approve-script` | Approve or edit the script, then shoot |
| POST | `/api/jobs/{id}/scenes/{i}/regenerate` | Re-shoot one scene (1 credit) |
| POST | `/api/jobs/{id}/scenes/{i}/takes/{t}/restore` | Restore an earlier take (free) |
| POST | `/api/jobs/{id}/global-edit` | Change a costume/set everywhere (1 credit per affected scene) |
| POST | `/api/jobs/{id}/timeline` | Reorder / trim / drop scenes — no generation, free |
| POST | `/api/jobs/{id}/export` | Reframe to 9:16 or 1:1 — no generation, free |
| GET/POST/DELETE | `/api/characters` | Character library, reusable across jobs |
| GET | `/api/credits` | Balance, ledger and what expires when |

Plus Stripe checkout/portal/webhook and an admin surface.

## Stack

- **Frontend:** Next.js 14, React 18, Tailwind CSS, 20 locales
- **Backend:** FastAPI, ffmpeg, MoviePy, httpx
- **Data:** Supabase (auth, storage, credit ledger), Stripe (billing)
- **AI:** Claude for script and storyboard; MuAPI / fal.ai / ElevenLabs for
  image, video, voice, music, SFX and lip sync

## Layout

```
server/
  api.py            FastAPI app
  jobs.py           Job store + SSE + cancellation
  agents/           Screenwriter, Storyboard Artist
  interfaces/       The decision modules — camera, pacing, shot_plan,
                    scene_take, video_backend, subtitles, score, reframe,
                    second_budget, colour grade, film look …
                    Domain reasoning lives here, not in the pipelines.
  pipelines/        idea2video, script2video — orchestration only
  tools/            Vendor adapters, one file per vendor per stage
  tests/            pytest, fully offline
client/
  app/[locale]/     Next.js app router
  lib/              i18n, Supabase, SEO
```

Every module in `interfaces/` opens with an essay arguing why it decides what
it decides, usually citing the delivered job that proved the old answer wrong.
Start there.

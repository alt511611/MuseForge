# MuseForge

**Agentic AI Video Studio** — turn a single text idea into a complete cinematic
micro-drama through a multi-agent pipeline powered by MuAPI and Claude AI.

```
Idea → Screenwriter → Storyboard Artist → Frame Generator → Video Generator → Final Drama
         (Claude)        (Claude)           (MuAPI)           (MuAPI)         (+ BGM)
```

## Why MuseForge

| Capability | MuseForge | Typical text-to-video tools |
|---|---|---|
| Character consistency across scenes | **Locked portrait, reused everywhere** | Drifts between shots |
| Director intent | **6 cinematic director presets** (lens, pacing, grade) | Prompt-only |
| Real-time transparency | **Live SSE agent log + storyboard preview** | Opaque progress bar |
| Try before you buy | **Full demo mode, no API key required** | Sign-up / credits first |
| Resilience | **Retry + backoff on every provider call** | Fails on first hiccup |
| Output | **In-browser player, download, per-scene gallery** | Download-only |

## Key Features

- **Character Consistency Lock** — one portrait per character, generated once and reused across every scene.
- **Director Style Presets** — Slow Cinematic, Balanced, Dynamic Action, Intimate, Noir Mystery, Anime.
- **Demo Mode** — no keys? The whole pipeline still runs with placeholder assets so you can explore the product instantly.
- **Real-time SSE Progress** — live agent log with a heartbeat that survives long generation stages.
- **Storyboard Gallery** — every generated frame and locked character portrait shown in the browser.
- **In-browser Player + Download** — watch and download the final drama.
- **Cancellable Jobs** — stop a running generation cleanly.
- **Render Estimate** — time/asset estimate before you commit.
- **Resilient Providers** — automatic retry with exponential backoff on transient MuAPI errors.

## Quick Start

### Demo mode (zero config)

```bash
# Backend
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python api.py            # runs in demo mode when no MUAPI_KEY is set

# Frontend (in another terminal)
cd client
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and generate a drama — no API keys needed.

### With real generation

```bash
cp .env.example server/.env
# edit server/.env and set MUAPI_KEY (+ optional ANTHROPIC_API_KEY)
```

### Docker (full stack)

```bash
docker compose up --build
```

### Tests

```bash
cd server
python -m pytest -v          # or: make test
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health + demo/keys status |
| GET | `/api/director-styles` | List director presets |
| POST | `/api/estimate` | Render time / asset estimate |
| POST | `/api/generate` | Start a generation job |
| GET | `/api/jobs/{id}` | Job status + result |
| GET | `/api/jobs/{id}/stream` | SSE progress stream (with heartbeat) |
| GET | `/api/jobs/{id}/video` | Stream/download the final video |
| POST | `/api/jobs/{id}/cancel` | Cancel a running job |

## Tech Stack

- **Frontend:** Next.js 14, React 18, Tailwind CSS
- **Backend:** FastAPI, MoviePy, httpx
- **AI:** MuAPI (image/video generation), Claude (script & storyboard)

## Project Layout

```
server/
  api.py                     FastAPI app (endpoints)
  jobs.py                    In-memory job store + SSE + cancellation
  agents/                    Screenwriter, Storyboard Artist
  interfaces/                Camera presets, character & shot models
  pipelines/                 idea2video + script2video orchestration
  tools/                     MuAPI client + image/video generators
  tests/                     pytest suite (runs fully offline)
client/
  app/                       Next.js app router (home + job view)
  components/IdeaForm.js     Idea input with live estimate
```

See `.env.example` for all configuration options.

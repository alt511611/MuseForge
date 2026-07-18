# MuseForge Deployment Notes

## Supabase Storage — Video Bucket (required for production)

Generated videos are uploaded to **Supabase Storage** so they survive Render
restarts and work across multiple instances. The local `/tmp/museforge_jobs`
directory is only a working scratch space.

### Create the bucket (Dashboard — not code)

1. Open **Supabase Dashboard → Storage**.
2. Create a new bucket named **`videos`**.
3. Set it to **Private** (not public). Signed URLs are issued by the API with
   the service role key (default TTL: 7 days).
4. No public read policy is required. The backend uses `SUPABASE_SERVICE_KEY`
   to upload and to mint signed URLs via:
   - `POST /storage/v1/object/videos/{job_id}.mp4`
   - `POST /storage/v1/object/sign/videos/{job_id}.mp4`

### Environment

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_KEY` | Service role key (server only) |
| `MUSEFORGE_STORAGE_BUCKET` | Optional; default `videos` |
| `MUSEFORGE_SIGNED_URL_TTL` | Optional; seconds (default `604800` = 7 days) |

In demo mode (`MUSEFORGE_DEMO=1`) or when Supabase env vars are missing, the
API **does not** call Storage — it returns the local path (same pattern as
MuAPI demo fallbacks).

### Disk cleanup

After a successful Storage upload, the job's local working directory is
removed. A background task also deletes orphan directories under
`MUSEFORGE_JOBS_DIR` that are older than 24 hours and not in the active
in-memory job list.

---

## Security headers

Applied on both the FastAPI backend and the Next.js frontend:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- Backend also sends `Strict-Transport-Security: max-age=63072000; includeSubDomains`

### Content-Security-Policy (future)

**Do not enable CSP yet** without careful testing. Stripe.js, Supabase Auth,
and any CDN domains must be allowlisted correctly; a misconfigured CSP will
break login, checkout, and video playback. Add CSP later behind a staging
checklist that covers Google OAuth, Stripe Checkout/Portal, and Supabase
Storage signed URLs.

---

## Optional background music (Creator/Pro) + Free-plan watermark

- `music_enabled` on `/api/generate` is only honoured for Creator/Pro plans
  (checked server-side against `profiles.plan`) and adds a flat **+1 credit**
  surcharge — silently ignored, never an error, for Free/anonymous requests.
  Never triggered in demo mode.
- Music generation (`server/tools/muapi_music_generator.py`) is best-effort:
  any failure is logged and the job continues without music.
- Watermarking (`server/pipelines/idea2video.py: add_watermark`) applies
  **only** to the Free plan — Creator and Pro are watermark-free. It burns a
  small, semi-transparent "MuseForge" text into the bottom-right corner via
  moviepy/ffmpeg, after the final video is concatenated.
- The watermark step needs a real TrueType font on the host. The backend
  `Dockerfile` installs `fonts-dejavu-core` for this; if you deploy without
  that Dockerfile (e.g. a bare Render/Railway Python buildpack), install a
  TTF font package or set `MUSEFORGE_WATERMARK_FONT` to an absolute font
  path. If no font is found, the watermark step **fails open** (video ships
  unwatermarked, job never fails) and logs a warning — check logs after
  deploying if Free-plan videos should be watermarked but aren't.

## Runbook reminders

1. Apply `supabase_migration.sql` (including `deduct_credits` RPC,
   `processed_stripe_events`, the `music_enabled`/`plan` columns on
   `public.jobs`, and the updated `plan_limits` view) before enabling paid
   generation.
2. Create the private `videos` Storage bucket before the first non-demo
   production render.
3. Set Stripe price IDs and webhook secret on Render.
4. Rebuild/redeploy the backend image after this change so the Dockerfile's
   `fonts-dejavu-core` install takes effect (see watermark section above).

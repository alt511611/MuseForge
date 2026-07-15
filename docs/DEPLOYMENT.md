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

## Runbook reminders

1. Apply `supabase_migration.sql` (including `deduct_credits` RPC and
   `processed_stripe_events`) before enabling paid generation.
2. Create the private `videos` Storage bucket before the first non-demo
   production render.
3. Set Stripe price IDs and webhook secret on Render.

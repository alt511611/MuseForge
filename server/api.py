"""MuseForge FastAPI backend."""

import json
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from auth import (
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
    AuthUser,
    get_current_admin,
    get_current_user,
    get_optional_user,
)
from interfaces.camera import DIRECTOR_STYLES
from jobs import JobStatus, job_store, run_generation_job

load_dotenv()

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"),
).split(",")

DEMO_FLAG = os.environ.get("MUSEFORGE_DEMO", "").lower() in ("1", "true", "yes")
SECONDS_PER_SCENE = float(os.environ.get("MUSEFORGE_SECONDS_PER_SCENE", "75"))


def _is_demo() -> bool:
    return DEMO_FLAG or not bool(os.environ.get("MUAPI_KEY"))


# ── Rate limiter (sliding-window, no external dependencies) ───────────────────

class _SlidingWindowRateLimiter:
    """Per-key sliding-window rate limiter using monotonic clock.

    Keeps a list of hit timestamps per key and trims them on every check.
    The memory footprint is bounded by limit * number_of_unique_keys.
    """

    def __init__(self, limit: int = 5, window: float = 60.0):
        self._limit = limit
        self._window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        hits = [t for t in self._hits[key] if t > cutoff]
        if len(hits) >= self._limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


# 5 generate requests per 60 s per authenticated user / IP
_rate_limiter = _SlidingWindowRateLimiter(limit=5, window=60.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.environ.get("MUSEFORGE_JOBS_DIR", "/tmp/museforge_jobs"), exist_ok=True)
    yield


app = FastAPI(title="MuseForge API", version="2.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    idea: str = Field(..., min_length=3, max_length=2000)
    style: str = "Cinematic"
    director_style: str = "cinematic_balanced"
    aspect_ratio: str = "16:9"
    num_scenes: int = Field(default=3, ge=2, le=5)
    user_requirement: str = ""
    character_image: Optional[str] = None
    character_name: str = ""


class GenerateResponse(BaseModel):
    job_id: str
    demo: bool


class EstimateRequest(BaseModel):
    num_scenes: int = Field(default=3, ge=2, le=5)


# ── Public endpoints ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "museforge-api",
        "version": "2.3.0",
        "demo_mode": _is_demo(),
        "muapi_configured": bool(os.environ.get("MUAPI_KEY")),
        "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "auth_configured": bool(SUPABASE_URL),
    }


@app.get("/api/stats")
async def public_stats():
    """Return public job counts for the live counter on the homepage."""
    total = 0
    monthly = 0
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                now = time.time()
                import datetime
                first_of_month = datetime.datetime.utcnow().replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                ).isoformat() + "Z"
                headers = {
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Prefer": "count=exact",
                    "Range": "0-0",
                }
                r_total = await client.get(
                    f"{SUPABASE_URL}/rest/v1/jobs?select=id&status=eq.completed",
                    headers=headers,
                )
                r_monthly = await client.get(
                    f"{SUPABASE_URL}/rest/v1/jobs?select=id&status=eq.completed&created_at=gte.{first_of_month}",
                    headers=headers,
                )
                if r_total.status_code == 206:
                    cr = r_total.headers.get("Content-Range", "")
                    total = int(cr.split("/")[-1]) if "/" in cr else 0
                if r_monthly.status_code == 206:
                    cr = r_monthly.headers.get("Content-Range", "")
                    monthly = int(cr.split("/")[-1]) if "/" in cr else 0
        except Exception:
            pass
    # Fall back to in-memory count when Supabase not configured
    if total == 0 and monthly == 0:
        jobs = list(job_store._jobs.values())
        total = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        monthly = total
    return {"total_completed": total, "monthly_completed": monthly}


@app.get("/api/director-styles")
async def director_styles():
    return {
        name: {
            "label": style.label,
            "default_lens": style.default_lens,
            "pacing": style.pacing,
            "color_grade": style.color_grade,
        }
        for name, style in DIRECTOR_STYLES.items()
    }


@app.post("/api/estimate")
async def estimate(req: EstimateRequest):
    demo = _is_demo()
    seconds = 5 if demo else int(req.num_scenes * SECONDS_PER_SCENE)
    return {
        "num_scenes": req.num_scenes,
        "estimated_seconds": seconds,
        "estimated_label": f"~{seconds}s" if seconds < 60 else f"~{round(seconds / 60, 1)} min",
        "asset_count": {
            "portraits": 1,
            "frames": req.num_scenes,
            "clips": req.num_scenes,
        },
        "demo": demo,
    }


# ── Credit helpers ────────────────────────────────────────────────────────────

async def _get_user_credits(user_id: str) -> int:
    """Return the current credit balance for a user. Returns -1 on Supabase error."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return 9999  # unlimited in dev
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={"id": f"eq.{user_id}", "select": "credits", "limit": "1"},
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            )
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("credits", 0)
    except Exception:
        pass
    return -1


async def _deduct_credits(user_id: str, amount: int, reason: str = "video_generation", job_id: str = "") -> bool:
    """Atomically deduct `amount` credits via Supabase RPC. Returns False if insufficient.

    Uses a PostgreSQL function that performs a single conditional UPDATE, preventing
    race conditions from the old read-then-write pattern.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return True
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            sb_headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
            }
            # Atomic deduction via RPC — returns new balance, or -1 if insufficient
            rpc_resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/deduct_credits",
                json={"p_user_id": user_id, "p_amount": amount},
                headers=sb_headers,
            )
            new_balance = rpc_resp.json()
            if new_balance == -1:
                return False  # insufficient credits
            # Fire-and-forget ledger entry
            ledger_payload = {"user_id": user_id, "amount": -amount, "reason": reason}
            if job_id:
                ledger_payload["job_id"] = job_id
            await client.post(
                f"{SUPABASE_URL}/rest/v1/credit_ledger",
                json=ledger_payload,
                headers={**sb_headers, "Prefer": "return=minimal"},
            )
        return True
    except Exception as exc:
        logger.error("_deduct_credits failed for user %s: %s", user_id, exc)
        return True  # fail-open: don't block generation on Supabase outages


# ── Generation (rate-limited; auth optional for demo mode) ───────────────────

@app.post("/api/generate", response_model=GenerateResponse)
async def generate(
    req: GenerateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Optional[AuthUser] = Depends(get_optional_user),
):
    if req.director_style not in DIRECTOR_STYLES:
        raise HTTPException(status_code=400, detail=f"Unknown director style: {req.director_style}")

    # Rate-limit key: authenticated user_id preferred; fallback to client IP
    rl_key = (
        current_user.user_id
        if current_user
        else (request.client.host if request.client else "anon")
    )
    if not _rate_limiter.allow(rl_key):
        raise HTTPException(
            status_code=429,
            detail="Çok fazla istek. Lütfen 1 dakika bekleyin ve tekrar deneyin.",
            headers={"Retry-After": "60"},
        )

    demo = _is_demo()
    api_key = os.environ.get("MUAPI_KEY", "")

    # Block unauthenticated users outside demo mode
    if not demo and current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in to generate videos.",
        )

    # Credit check — only for authenticated non-demo requests
    if current_user and not demo:
        ok = await _deduct_credits(current_user.user_id, req.num_scenes, "video_generation")
        if not ok:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. You need {req.num_scenes} credits for this generation. Please top up your balance.",
            )

    job = await job_store.create(
        idea=req.idea,
        style=req.style,
        director_style=req.director_style,
        aspect_ratio=req.aspect_ratio,
        num_scenes=req.num_scenes,
        user_requirement=req.user_requirement,
        demo=demo,
        user_id=current_user.user_id if current_user else None,
        user_email=current_user.email if current_user else None,
        character_image=req.character_image,
        character_name=req.character_name,
    )

    background_tasks.add_task(run_generation_job, job, api_key)
    return GenerateResponse(job_id=job.id, demo=demo)


# ── Job endpoints (auth optional for public demo jobs) ───────────────────────

@app.get("/api/jobs/{job_id}")
async def get_job(
    job_id: str,
    current_user: Optional[AuthUser] = Depends(get_optional_user),
):
    job = job_store.get(job_id)
    if job:
        # Auth guard for in-memory jobs
        if current_user and job.user_id and job.user_id != current_user.user_id:
            if not current_user.is_admin:
                raise HTTPException(status_code=403, detail="Access denied")
        return job.to_dict()

    # Cache miss (post-restart): try Supabase
    data = await job_store.get_or_fetch_dict(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    if current_user and data.get("user_id") and data["user_id"] != current_user.user_id:
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Access denied")
    return data


@app.get("/api/jobs/{job_id}/video")
async def get_job_video(job_id: str):
    job = job_store.get(job_id)

    if job:
        result = job.result
    else:
        # Post-restart fallback
        data = await job_store.get_or_fetch_dict(job_id)
        result = data.get("result") if data else None

    if not result:
        raise HTTPException(status_code=404, detail="Video not ready")

    path = result.get("video_path")
    if path and os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=f"museforge_{job_id}.mp4")

    url = result.get("video_url")
    if url:
        return RedirectResponse(url)

    raise HTTPException(status_code=404, detail="Video not available")


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        async for event in job_store.subscribe(job_id):
            yield f"data: {json.dumps(event.to_dict())}\n\n"
        final = job_store.get(job_id)
        if final:
            yield f"data: {json.dumps({'stage': 'done', 'status': final.status.value, 'progress': 100})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: Optional[AuthUser] = Depends(get_optional_user),
):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Job already finished")
    if current_user and job.user_id and job.user_id != current_user.user_id:
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Access denied")
    job.status = JobStatus.CANCELLED
    await job_store.persist(job)
    return {"status": "cancelled"}


# ── Auth helper ───────────────────────────────────────────────────────────────

@app.get("/api/me")
async def me(current_user: AuthUser = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "role": current_user.role,
        "is_admin": current_user.is_admin,
    }


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.get("/api/admin/stats")
async def admin_stats(_admin: AuthUser = Depends(get_current_admin)):
    jobs = list(job_store._jobs.values())
    total = len(jobs)
    return {
        "total": total,
        "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
        "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
        "running": sum(1 for j in jobs if j.status == JobStatus.RUNNING),
        "queued": sum(1 for j in jobs if j.status == JobStatus.QUEUED),
        "cancelled": sum(1 for j in jobs if j.status == JobStatus.CANCELLED),
    }


@app.get("/api/admin/jobs")
async def admin_list_jobs(
    limit: int = 50,
    offset: int = 0,
    _admin: AuthUser = Depends(get_current_admin),
):
    jobs = sorted(job_store._jobs.values(), key=lambda j: j.created_at, reverse=True)
    page = jobs[offset: offset + limit]
    return {
        "total": len(jobs),
        "jobs": [j.to_dict(include_events=False) for j in page],
    }


@app.get("/api/admin/jobs/{job_id}")
async def admin_get_job(job_id: str, _admin: AuthUser = Depends(get_current_admin)):
    job = job_store.get(job_id)
    if job:
        return job.to_dict(include_events=True)
    data = await job_store.get_or_fetch_dict(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")
    return data


@app.post("/api/admin/jobs/{job_id}/retry")
async def admin_retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    _admin: AuthUser = Depends(get_current_admin),
):
    old = job_store.get(job_id)
    if not old:
        raise HTTPException(status_code=404, detail="Job not found")
    if old.status == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is still running")

    new_job = await job_store.create(
        idea=old.idea,
        style=old.style,
        director_style=old.director_style,
        aspect_ratio=old.aspect_ratio,
        num_scenes=old.num_scenes,
        user_requirement=old.user_requirement,
        demo=old.demo,
        user_id=old.user_id,
        user_email=old.user_email,
    )
    api_key = os.environ.get("MUAPI_KEY", "")
    background_tasks.add_task(run_generation_job, new_job, api_key)
    return {"new_job_id": new_job.id}


@app.delete("/api/admin/jobs/{job_id}")
async def admin_delete_job(job_id: str, _admin: AuthUser = Depends(get_current_admin)):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.RUNNING:
        job.status = JobStatus.CANCELLED
    await job_store.delete(job_id)
    return {"deleted": job_id}


# ── Credits endpoints ─────────────────────────────────────────────────────────

@app.get("/api/credits")
async def get_credits(current_user: AuthUser = Depends(get_current_user)):
    """Return current credit balance and recent ledger entries."""
    credits = await _get_user_credits(current_user.user_id)
    ledger = []
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/credit_ledger",
                    params={
                        "user_id": f"eq.{current_user.user_id}",
                        "select": "amount,reason,job_id,created_at",
                        "order": "created_at.desc",
                        "limit": "20",
                    },
                    headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                )
                ledger = resp.json() if isinstance(resp.json(), list) else []
        except Exception:
            pass
    return {"credits": credits, "ledger": ledger}


# ── Stripe endpoints ──────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str
    success_url: str
    cancel_url: str


class PortalRequest(BaseModel):
    return_url: str


@app.post("/api/create-checkout-session")
async def create_checkout_session(
    req: CheckoutRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    from stripe_integration import create_checkout_session as _create, get_price_id

    price_id = get_price_id(req.plan)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe price configured for plan '{req.plan}'.",
        )
    try:
        url = await _create(
            price_id=price_id,
            user_id=current_user.user_id,
            user_email=current_user.email,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
        )
        return {"url": url}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class BuyCreditsRequest(BaseModel):
    package: str  # SMALL | MEDIUM | LARGE
    success_url: str
    cancel_url: str


@app.post("/api/buy-credits")
async def buy_credits(
    req: BuyCreditsRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Create a one-time Stripe Checkout session for a credit package."""
    from stripe_integration import create_checkout_session as _create, get_credit_price_id, CREDIT_PACKAGES

    pkg_key = req.package.upper()
    if pkg_key not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown credit package: {req.package}")

    price_id = get_credit_price_id(pkg_key)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe price configured for credit package '{req.package}'. Set STRIPE_PRICE_CREDITS_{pkg_key} env var.",
        )
    try:
        url = await _create(
            price_id=price_id,
            user_id=current_user.user_id,
            user_email=current_user.email,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
            mode="payment",
            metadata={"credit_package": pkg_key},
        )
        return {"url": url, "package": pkg_key, "credits": CREDIT_PACKAGES[pkg_key]["credits"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/stripe-portal")
async def stripe_portal(
    req: PortalRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Create a Stripe Billing Portal session for the authenticated user."""
    from stripe_integration import create_portal_session

    customer_id: Optional[str] = None
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/profiles",
                    params={
                        "id": f"eq.{current_user.user_id}",
                        "select": "stripe_customer_id",
                        "limit": "1",
                    },
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    },
                )
                data = resp.json()
                if isinstance(data, list) and data:
                    customer_id = data[0].get("stripe_customer_id")
        except Exception:
            pass

    if not customer_id:
        raise HTTPException(
            status_code=400,
            detail="Bu hesap için Stripe müşteri kaydı bulunamadı. Önce bir abonelik başlatın.",
        )

    try:
        url = await create_portal_session(
            customer_id=customer_id,
            return_url=req.return_url,
        )
        return {"url": url}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/stripe-webhook")
async def stripe_webhook(request: Request):
    from stripe_integration import handle_webhook

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        result = await handle_webhook(payload, sig)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

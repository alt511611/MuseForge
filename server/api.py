"""MuseForge FastAPI backend."""

import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from interfaces.camera import DIRECTOR_STYLES
from jobs import JobStatus, job_store, run_generation_job

load_dotenv()

ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

DEMO_FLAG = os.environ.get("MUSEFORGE_DEMO", "").lower() in ("1", "true", "yes")

# Rough per-scene wall-clock cost for the estimate endpoint (storyboard + frame + clip).
SECONDS_PER_SCENE = float(os.environ.get("MUSEFORGE_SECONDS_PER_SCENE", "75"))


def _is_demo() -> bool:
    """Demo mode runs the whole pipeline with placeholder assets — no API key required."""
    return DEMO_FLAG or not bool(os.environ.get("MUAPI_KEY"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.environ.get("MUSEFORGE_JOBS_DIR", "/tmp/museforge_jobs"), exist_ok=True)
    yield


app = FastAPI(title="MuseForge API", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    idea: str = Field(..., min_length=3, max_length=2000)
    style: str = "Cinematic"
    director_style: str = "cinematic_balanced"
    aspect_ratio: str = "16:9"
    num_scenes: int = Field(default=3, ge=2, le=5)
    user_requirement: str = ""


class GenerateResponse(BaseModel):
    job_id: str
    demo: bool


class EstimateRequest(BaseModel):
    num_scenes: int = Field(default=3, ge=2, le=5)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "museforge-api",
        "version": "2.1.0",
        "demo_mode": _is_demo(),
        "muapi_configured": bool(os.environ.get("MUAPI_KEY")),
        "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


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


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    if req.director_style not in DIRECTOR_STYLES:
        raise HTTPException(status_code=400, detail=f"Unknown director style: {req.director_style}")

    demo = _is_demo()
    api_key = os.environ.get("MUAPI_KEY", "")

    job = await job_store.create(
        idea=req.idea,
        style=req.style,
        director_style=req.director_style,
        aspect_ratio=req.aspect_ratio,
        num_scenes=req.num_scenes,
        user_requirement=req.user_requirement,
        demo=demo,
    )

    background_tasks.add_task(run_generation_job, job, api_key)
    return GenerateResponse(job_id=job.id, demo=demo)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/video")
async def get_job_video(job_id: str):
    job = job_store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Video not ready")

    path = job.result.get("video_path")
    if path and os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=f"museforge_{job_id}.mp4")

    url = job.result.get("video_url")
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Job already finished")
    job.status = JobStatus.CANCELLED
    return {"status": "cancelled"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

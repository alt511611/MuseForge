FROM python:3.11-slim

# ffmpeg is required by moviepy for real (non-demo) video assembly.
# fonts-dejavu-core provides the TTF font used to render the Free-plan
# watermark (server/pipelines/idea2video.py:add_watermark) — without it the
# watermark step fails open (video ships unwatermarked) rather than erroring.
# curl is what an orchestrator's container healthcheck shells out to. It is
# not used by any application code, so it looks removable and is not: a
# scheduler that cannot ask this image whether it is healthy assumes it is
# NOT. python:3.11-slim ships neither curl nor wget, and a deploy of a
# perfectly working container was rolled back over exactly that -- uvicorn had
# logged "Application startup complete" while the probe reported
# "/bin/sh: 1: curl: not found" ten times and the platform called it unhealthy.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

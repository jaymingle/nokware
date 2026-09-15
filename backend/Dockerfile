# Nokware's API. Built by Coolify from this directory; see docs/DEPLOYMENT.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, within the versions the tests pass on, so a code change doesn't reinstall them.
COPY pyproject.toml constraints.txt ./
COPY app ./app
RUN pip install -c constraints.txt .

# Voice notes need PyAV's bundled FFmpeg to encode Opus, and MP3 as the fallback: stop the build if it can't.
RUN python -c "import av; av.codec.Codec('libopus', 'w'); av.codec.Codec('libmp3lame', 'w')"

# The schema and cleanup scripts, to run inside the container (docker exec … python scripts/…).
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 nokware
USER nokware

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status != 200)"

# One worker, always: the scheduled jobs (the Ledger's deadline job, the petition clock, the purge) and the
# per-record locks live in the process, so a second worker would run them twice. Proxy headers, so the rate
# limits see each resident's own address rather than Coolify's proxy; safe only because the container's port
# is reached through that proxy and never published directly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

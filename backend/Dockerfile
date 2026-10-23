# ClawBack backend as a container, for a container host (for example a Nebius serverless endpoint).
# The VM route in deploy/vm/ doesn't need this file. See docs/DEPLOY.md.
#
# Build from the backend folder:
#   docker build -t clawback-backend backend
# Run, with the settings in an env file kept outside the repo and a volume for the database:
#   docker run --env-file clawback.env -v clawback-data:/data -p 8000:8000 clawback-backend
#
# backend/.env is never copied in (see .dockerignore). Pass settings as environment variables.

FROM python:3.12-slim

# CLAWBACK_DOTENV=0: settings come from the environment only, never from a .env file inside the image.
# Everything that must survive a restart lives under /data. Mount a volume there.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CLAWBACK_DOTENV=0 \
    CLAWBACK_DB_PATH=/data/clawback.db \
    CLAWBACK_CONNECTIONS_FILE=/data/connections.json

WORKDIR /app

# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml ./
COPY clawback ./clawback
RUN pip install .

RUN useradd --system --uid 10001 --home-dir /app clawback \
    && mkdir -p /data \
    && chown clawback:clawback /data
USER clawback
VOLUME ["/data"]

EXPOSE 8000

# One worker: sign-in state is kept in memory, so every request must reach the same process.
CMD ["python", "-m", "uvicorn", "clawback.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

# Multi-stage build (design D9). The build stage needs uv and a full
# resolver run; the runtime stage copies only the finished virtualenv, so
# neither uv nor pytest (a dev-only dependency group) ever ships.

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY manga_tracker/ manga_tracker/
# --frozen: never resolves, only installs exactly what uv.lock pins.
# --no-dev: pytest must never reach the image that actually runs.
RUN uv sync --frozen --no-dev

# Panel frontend (V1b). Node exists only here, never in the runtime image —
# the same rule that keeps uv and pytest out. package*.json is copied alone
# first so the npm ci layer survives source-only edits.
FROM node:24-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
# OS tzdata (design D9, unverified claim #1): active_sweep's cron trigger
# uses a local hour, and zoneinfo/tzlocal read the system tz database on
# Linux - a slim image is not guaranteed to carry it already.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Fixed non-root UID: SQLite needs write permission on data/'s *directory* in
# every journal mode (WAL writes -wal/-shm, rollback-journal writes
# -journal, not just WAL) - chown ./data to this same UID once on the host.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=frontend-build /frontend/dist frontend/dist
COPY manga_tracker/ manga_tracker/
COPY seed-plantilla.csv ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
# No HEALTHCHECK: there is no port to probe. The weekly heartbeat (out of
# scope this phase) is the designed liveness signal, not an HTTP endpoint.
ENTRYPOINT ["python", "-m", "manga_tracker"]
CMD ["run"]

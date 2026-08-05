# Scheduler & Deployment Specification

## Purpose

APScheduler wiring for the two jobs in scope this phase, one Docker container, SQLite on a volume, and startup validation (one-pager-v1a.md §"Decisiones de plataforma cerradas", "Fases internas de V1a").

## Requirements

### Requirement: Only two jobs registered this phase

The scheduler MUST register exactly `feed_check` (hourly) and `active_sweep` (daily); it MUST NOT register `onhold_sweep`, which is out of scope for this phase (one-pager-v1a.md §"Fases internas de V1a"; v1a-heart-phase proposal "Scope — out").

#### Scenario: Only two jobs present

- GIVEN the process starts
- WHEN the scheduler is inspected
- THEN it lists `feed_check` and `active_sweep` and no `onhold_sweep` entry

### Requirement: One process, one container, no host cron

The scheduler MUST run in-process within the single application container; no host-level cron or second process MUST be introduced (one-pager-v1a.md §"Decisiones de plataforma cerradas").

#### Scenario: Single container deployment

- GIVEN the Docker image is built and run
- WHEN it starts
- THEN one container hosts both the scheduler and the application, with no external cron dependency

### Requirement: SQLite file on a mounted volume

The database file MUST live under `data/`, mounted as a Docker volume, so it survives container recreation (one-pager-v1a.md §"Decisiones de plataforma cerradas"; spec-seed-manual.md §"El archivo").

#### Scenario: Data survives container recreation

- GIVEN the container is recreated
- WHEN it starts again with the same volume mounted
- THEN the existing database file is used, not recreated empty

### Requirement: Startup fails fast without required env vars

The process MUST validate the Telegram token and chat id environment variables at startup and MUST refuse to start the scheduler if either is missing (spec-bot-telegram.md §"Configuración y token").

#### Scenario: Missing chat id blocks startup

- GIVEN the chat id environment variable is unset
- WHEN the process starts
- THEN it exits with a clear error before any job is scheduled

### Requirement: No two instances of the same job run concurrently

The scheduler MUST NOT start a new run of a job while a previous run of that same job is still active (spec-cliente-fuente-descubrimiento.md §"Solapamiento").

#### Scenario: Overlapping trigger is skipped

- GIVEN `active_sweep`'s prior run is still executing
- WHEN its next scheduled trigger fires
- THEN the new run is skipped and the skip is logged

### Requirement: Sequential requests only

The deployment MUST NOT introduce concurrency at the process or request level beyond what source-client and chapter-detection already specify (one-pager-v1a.md §"Arquitectura de descubrimiento").

#### Scenario: No parallel workers

- GIVEN the container runs
- WHEN jobs execute
- THEN no additional worker processes or threads issue concurrent source requests

## References

- one-pager-v1a.md v1.5

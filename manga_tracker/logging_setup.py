"""stdlib `logging` to stdout, plain text, UTC (design D8). A per-run
`LoggerAdapter` carries the `job_runs` id down the call chain; a record
logged outside a run still needs `job_name`/`run_id` for the format string,
so a filter defaults them to `-`. Rotation is Docker's job, not this one's."""

import logging
import sys
import time

_FORMAT = "%(asctime)s %(levelname)s [%(job_name)s:%(run_id)s] %(name)s: %(message)s"


def _default_run_fields(record: logging.LogRecord) -> bool:
    record.job_name = getattr(record, "job_name", "-")
    record.run_id = getattr(record, "run_id", "-")
    return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stdout, level=level, format=_FORMAT, datefmt="%Y-%m-%dT%H:%M:%SZ", force=True)
    logging.getLogger().handlers[0].addFilter(_default_run_fields)
    logging.Formatter.converter = time.gmtime  # UTC, per design's "timestamps stay UTC"


def run_logger(job_name: str, run_id: int) -> logging.LoggerAdapter:
    """Logger stamping `job_name`/`run_id` on every line for one run."""
    return logging.LoggerAdapter(logging.getLogger(job_name), {"job_name": job_name, "run_id": run_id})

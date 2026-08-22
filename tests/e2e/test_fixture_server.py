"""The one Applicable threat-matrix row for phase 2 (design D11): the
Playwright `webServer` spawns a real server subprocess, so this guard pins
that `tests/e2e/fixture_server.py` refuses to point at the configured
production DB path — an E2E harness must never be able to reach production
data."""

import pytest

from tests.e2e.fixture_server import check_not_production_db


def test_refuses_to_start_against_the_production_db_path(monkeypatch, tmp_path):
    production_path = str(tmp_path / "production.db")
    monkeypatch.setenv("DB_PATH", production_path)

    with pytest.raises(RuntimeError, match="production DB path"):
        check_not_production_db(production_path)


def test_accepts_a_path_that_is_not_the_production_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "production.db"))

    check_not_production_db(str(tmp_path / "fixture.db"))  # must not raise

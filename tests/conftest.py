"""Shared fixtures. No test may reach a real socket — manganato and
Telegram are both reached through injected fakes."""

import socket

import pytest


@pytest.fixture(autouse=True)
def block_network_sockets(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise RuntimeError("Network access is blocked in tests — inject a fake Transport/Sender instead.")

    monkeypatch.setattr(socket.socket, "connect", _blocked)

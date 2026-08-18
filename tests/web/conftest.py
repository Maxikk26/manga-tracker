"""Narrows the parent conftest's socket block to "loopback only" for the web
suite. TestClient drives the app through ASGI in-process — no HTTP leaves the
machine — but on Windows asyncio's proactor loop builds its self-pipe with
socket.socketpair(), which the stdlib emulates by connecting to 127.0.0.1.
That handshake is not network. Anything that tries to leave the machine
(manganato, Telegram) still fails exactly like everywhere else."""

import socket

import pytest

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@pytest.fixture(autouse=True)
def block_network_sockets(monkeypatch):
    # Same name as the parent fixture on purpose: pytest resolves to the
    # closest conftest, so this replaces the blanket block for tests/web only.
    real_connect = socket.socket.connect

    def _loopback_only(sock, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host in _LOOPBACK_HOSTS:
            return real_connect(sock, address, *args, **kwargs)
        raise RuntimeError("Network access is blocked in tests — inject a fake Transport/Sender instead.")

    monkeypatch.setattr(socket.socket, "connect", _loopback_only)

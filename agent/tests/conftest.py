"""Global deterministic-suite safety fixtures."""

from __future__ import annotations

import ipaddress
import socket

import pytest


def _is_loopback_host(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if host in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _deny_public_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    if request.node.get_closest_marker("requires_llm") or request.node.get_closest_marker("release_e2e"):
        return
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) and address else None
        if not _is_loopback_host(host):
            raise OSError("deterministic test network denied")
        return original_connect(sock, address)

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else None
        if not _is_loopback_host(host):
            raise OSError("deterministic test network denied")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)

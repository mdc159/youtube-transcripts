"""Unit tests for dns_fallback.py (no network)."""
from __future__ import annotations

import socket

import pytest

from yt_distill.core import dns_fallback as df


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(df, "_cache", {})
    yield
    socket.getaddrinfo = df._orig_getaddrinfo


def test_passthrough_when_resolution_succeeds(monkeypatch):
    sentinel = [("ok",)]
    monkeypatch.setattr(df, "_orig_getaddrinfo", lambda *a, **k: sentinel)
    monkeypatch.setattr(df, "doh_resolve",
                        lambda h: pytest.fail("DoH must not run on success"))
    assert df._fallback_getaddrinfo("example.com", 443) == sentinel


def test_fallback_resolves_via_doh_and_caches(monkeypatch):
    calls = {"doh": 0}

    def orig(host, port, *a, **k):
        if host == "blocked.example":
            raise socket.gaierror(8, "nodename nor servname provided")
        return [(host, port)]

    def fake_doh(host):
        calls["doh"] += 1
        return "192.0.2.7"

    monkeypatch.setattr(df, "_orig_getaddrinfo", orig)
    monkeypatch.setattr(df, "doh_resolve", fake_doh)

    assert df._fallback_getaddrinfo("blocked.example", 443) == [("192.0.2.7", 443)]
    # Second lookup hits the cache — DoH queried exactly once.
    assert df._fallback_getaddrinfo("blocked.example", 80) == [("192.0.2.7", 80)]
    assert calls["doh"] == 1


def test_fallback_reraises_when_doh_also_fails(monkeypatch):
    def orig(host, port, *a, **k):
        raise socket.gaierror(8, "no")

    monkeypatch.setattr(df, "_orig_getaddrinfo", orig)
    monkeypatch.setattr(df, "doh_resolve", lambda h: None)
    with pytest.raises(socket.gaierror):
        df._fallback_getaddrinfo("gone.example", 443)


def test_install_is_idempotent():
    df.install()
    first = socket.getaddrinfo
    df.install()
    assert socket.getaddrinfo is first
    assert socket.getaddrinfo is df._fallback_getaddrinfo


def test_doh_resolve_parses_answer(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return (b'{"Answer": [{"type": 5, "data": "cname.example."},'
                    b'{"type": 1, "data": "203.0.113.9"}]}')

    monkeypatch.setattr(df.urllib.request, "urlopen", lambda req, timeout: FakeResp())
    assert df.doh_resolve("bit.ly") == "203.0.113.9"


def test_doh_resolve_endpoint_redundancy(monkeypatch):
    """First endpoint dead → second answers."""
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise OSError("endpoint down")

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"Answer": [{"type": 1, "data": "198.51.100.4"}]}'

        return R()

    monkeypatch.setattr(df.urllib.request, "urlopen", fake_urlopen)
    assert df.doh_resolve("bit.ly") == "198.51.100.4"
    assert len(calls) == 2

"""Held sessions and transport thread-safety (docs/SESSION_DESIGN.md).

Before this, every call opened a TCP connection AND performed a login, then closed it —
the bridge's poller doing that per gateway every 30 s across 31 call sites. The transport
always had the machinery (idempotent connect, reconnect-and-re-login, retry); what was
missing was a way to hold a session without `with` closing it, and a lock making a held
client safe to share.
"""

from __future__ import annotations

import threading

import pytest

from franklinwh_direct_connect_api.client import LocalClient
from franklinwh_direct_connect_api.emulator import Emulator


@pytest.fixture
def emulator():
    emu = Emulator("127.0.0.1", 0).start()
    yield emu
    emu.stop()


def _client(emu) -> LocalClient:
    return LocalClient("127.0.0.1", emu.port, timeout=5.0)


# -- the point of the exercise ----------------------------------------------
def test_a_held_session_makes_one_connection_for_many_calls(emulator):
    """The whole reason this exists: N calls used to mean N connects and N logins."""
    c = _client(emulator)
    c.ensure_session()
    for _ in range(8):
        c.ensure_session()          # idempotent — must not reconnect
        c.power_flow()
    assert c.connects == 1, "a held session must not reopen the socket per call"
    c.close()


def test_with_still_closes_on_exit(emulator):
    """Existing code and every documented example rely on this. Unchanged."""
    with _client(emulator) as c:
        c.login()
        c.power_flow()
    assert c.connected is False


def test_a_closed_held_client_reconnects_on_next_use(emulator):
    """close() must leave the client usable, not spent."""
    c = _client(emulator)
    c.ensure_session()
    c.power_flow()
    c.close()
    assert c.connected is False
    c.ensure_session()
    c.power_flow()
    assert c.connects == 2, "exactly one reconnect, not a reconnect per call"
    c.close()


def test_ensure_session_is_idempotent_and_cheap(emulator):
    c = _client(emulator)
    for _ in range(5):
        c.ensure_session()
    assert c.connects == 1
    c.close()


# -- thread safety: the blocker that made persistence a trap -----------------
def test_concurrent_callers_on_one_held_client_do_not_thrash_the_socket(emulator):
    """Measured, not assumed: 6 threads x 12 calls on one held client makes
    **1 connect with the lock and 5 without**.

    The failure mode is NOT corrupted data, as first supposed. Unlocked, concurrent
    callers interleave on one socket, each other's frames time out, and `request()`
    reconnects and retries — so the *results* still come back correct, paid for in
    reconnect storms and latency. The retry machinery masks the race, which is why the
    obvious assertions (no exceptions, well-formed responses) pass either way and prove
    nothing. The connect count is the signal that discriminates."""
    c = _client(emulator)
    c.ensure_session()
    errors: list[BaseException] = []
    results: list[dict] = []

    def worker():
        try:
            for _ in range(12):
                results.append(c.power_flow())
        except BaseException as e:     # noqa: BLE001 — the point is to catch anything
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"concurrent use raised: {errors[:3]}"
    assert len(results) == 72
    assert all(isinstance(r, dict) and "soc" in r for r in results)
    # THE assertion. Without the lock this is ~5; the others above pass regardless.
    assert c.connects == 1, "contention must queue on the socket, not reopen it"
    c.close()


def test_the_transport_exposes_its_connect_count(emulator):
    """Without a counter, "the session is being reused" is unverifiable — which is how
    38 TIME_WAIT sockets a minute went unnoticed downstream."""
    c = _client(emulator)
    assert c.connects == 0
    c.ensure_session()
    assert c.connects == 1
    c.close()

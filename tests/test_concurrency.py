"""One lease, several threads.

An agent is routinely more than one thread: the MCP SDK runs synchronous tool
bodies in a worker pool, so two calls under a single lease genuinely execute in
parallel. That is the case where an interlock checked separately from the
switching it guards stops being an interlock, so it gets its own file.

Each test widens the check-to-apply window with a sleep in the backend. The
window is real without it -- a crosspoint takes milliseconds to settle -- the
sleep only makes the race land every run instead of one run in a hundred.
"""

from __future__ import annotations

import contextlib
import threading
import time

import pytest

from pickering_lxi_mcp import interlocks
from pickering_lxi_mcp.errors import InterlockError
from pickering_lxi_mcp.topology import Operation

CONFIRM = "the fixture is safe to energise"


def slow_close(session, delay: float = 0.02):
    real = session.backend.close_crosspoint

    def slow(*args, **kwargs):
        time.sleep(delay)
        return real(*args, **kwargs)

    session.backend.close_crosspoint = slow


def in_parallel(fns):
    errors: list[Exception] = []

    def wrap(fn):
        def run():
            try:
                fn()
            except Exception as exc:
                errors.append(exc)

        return run

    threads = [threading.Thread(target=wrap(fn)) for fn in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def shorted(session) -> bool:
    components = interlocks.connectivity(session.topology, session._closed_operations())
    return components.connected(
        session.topology.endpoint("psu_pos").node, session.topology.endpoint("gnd").node
    )


def test_two_threads_cannot_compose_a_short(armed):
    """The regression test for the bug this file exists for.

    psu_pos -> dut_pin_a1 and gnd -> dut_pin_a1 are each fine on their own and
    forbidden together. Run concurrently against a check that is not atomic with
    its apply, both pass their check, both switch, and the fixture is shorted.
    """
    session, token = armed
    slow_close(session)

    errors = in_parallel([
        lambda: session.route(token, "psu_pos", "dut_pin_a1"),
        lambda: session.route(token, "gnd", "dut_pin_a1"),
    ])

    assert not shorted(session), "the interlock was walked through by two threads"
    assert len(errors) == 1, f"exactly one route must be refused, got {errors}"
    assert isinstance(errors[0], InterlockError)
    assert len(session.routes) == 1
    assert session.subunit_state("matrix_a", 1)["closed_count"] == 1


@pytest.mark.parametrize("attempt", range(5))
def test_the_refusal_is_not_a_coin_flip(armed, attempt):
    """Whichever thread loses, the outcome is the same shape."""
    session, token = armed
    slow_close(session, delay=0.005)
    errors = in_parallel([
        lambda: session.route(token, "psu_pos", "dut_pin_a1"),
        lambda: session.route(token, "gnd", "dut_pin_a1"),
    ])
    assert not shorted(session)
    assert len(errors) == 1


def test_independent_routes_still_run_concurrently(armed):
    """Serialising must not mean refusing: unrelated work all lands."""
    session, token = armed
    slow_close(session, delay=0.01)

    pairs = [
        ("scope_ch1", "dut_pin_a1"),
        ("scope_ch2", "dut_pin_a2"),
        ("dmm_hi", "dut_pin_a3"),
        ("awg_out", "dut_pin_a4"),
    ]
    errors = in_parallel([lambda p=p: session.route(token, *p) for p in pairs])

    assert errors == []
    assert len(session.routes) == 4
    assert session.subunit_state("matrix_a", 1)["closed_count"] == 4


def test_concurrent_teardown_respects_the_reference_count(armed):
    """Two routes share a crosspoint; dropping both at once must not double-open."""
    session, token = armed
    session.route(token, "dmm_hi", "rtd_1")
    session.route(token, "dmm_hi", "rtd_2")
    shared = Operation("matrix_a", 1, 6, 14)
    assert session.backend.view_crosspoint("matrix_a", 1, 6, 14) is True

    errors = in_parallel([
        lambda: session.unroute(token, "dmm_hi", "rtd_1"),
        lambda: session.unroute(token, "dmm_hi", "rtd_2"),
    ])

    assert errors == []
    assert session.routes == {}
    assert session.backend.view_crosspoint(
        shared.card, shared.subunit, shared.row, shared.column
    ) is False


def test_observation_does_not_blow_up_while_the_table_is_moving(armed):
    """Reads run constantly and must never see a half-written route table."""
    session, token = armed
    slow_close(session, delay=0.004)
    seen: list[int] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            seen.append(len(session.list_routes()))
            session.interlock_status()
            session.crosspoint("matrix_a", 1, 4, 1)

    watcher = threading.Thread(target=reader)
    watcher.start()
    try:
        in_parallel([
            lambda: session.route(token, "scope_ch1", "dut_pin_a1"),
            lambda: session.route(token, "scope_ch2", "dut_pin_a2"),
            lambda: session.route(token, "dmm_hi", "dut_pin_a3"),
        ])
    finally:
        stop.set()
        watcher.join()

    assert seen, "the reader made progress rather than blocking behind the writers"
    assert len(session.routes) == 3


def test_two_owners_cannot_both_hold_the_chassis(session):
    """The reservation is what makes any of the above a single-writer problem."""
    taken: list[str] = []

    def grab(owner: str):
        with contextlib.suppress(Exception):  # losing is the expected outcome for one
            taken.append(session.reserve(owner=owner).owner)

    in_parallel([lambda: grab("alice"), lambda: grab("mallory")])
    assert len(set(taken)) == 1, f"two owners were both granted the chassis: {taken}"

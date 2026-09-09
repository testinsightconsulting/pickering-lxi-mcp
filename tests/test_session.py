"""Session lifecycle: reservations, reference-counted teardown, rollback."""

from __future__ import annotations

import time

import pytest

from pickering_lxi_mcp.errors import DriverError, InterlockError, ReservationError
from pickering_lxi_mcp.session import ChassisSession, route_id
from pickering_lxi_mcp.topology import Operation

CONFIRM = "the fixture is safe to energise"


def test_route_ids_are_undirected():
    assert route_id("a", "b") == route_id("b", "a")


def test_observation_needs_no_reservation(session):
    assert session.describe()["open_routes"] == 0
    assert session.subunit_state("matrix_a", 1)["closed_count"] == 0
    assert session.list_endpoints()
    assert session.interlock_status()["armed"] is False


def test_mutation_without_a_reservation_is_refused(session):
    with pytest.raises(ReservationError, match="no reservation"):
        session.route("anything", "scope_ch1", "dut_pin_a1")


def test_a_second_owner_cannot_take_a_reserved_chassis(session):
    session.reserve(owner="alice")
    with pytest.raises(ReservationError, match="reserved by 'alice'"):
        session.reserve(owner="mallory")


def test_the_same_owner_reserving_twice_gets_the_same_token(session):
    first = session.reserve(owner="alice")
    assert session.reserve(owner="alice").token == first.token


def test_an_expired_reservation_stops_working(session):
    token = session.reserve(owner="alice", ttl_seconds=0.01).token
    time.sleep(0.02)
    with pytest.raises(ReservationError, match="expired"):
        session.arm(token, CONFIRM)
    assert session.reservation is None


def test_a_zero_ttl_is_refused(session):
    with pytest.raises(ValueError, match="must be positive"):
        session.reserve(owner="alice", ttl_seconds=0)


def test_arming_needs_the_words_not_a_boolean(armed):
    session, _ = armed
    assert session.armed is True

    token = session.reserve(owner="pytest").token
    session.disarm(token)
    with pytest.raises(InterlockError, match="requires confirm"):
        session.arm(token, "yes")
    assert session.armed is False


def test_routing_closes_exactly_the_planned_crosspoints(armed):
    session, token = armed
    result = session.route(token, "scope_ch1", "dut_pin_a1")
    assert result["status"] == "open"
    assert session.backend.view_crosspoint("matrix_a", 1, 4, 1) is True
    assert session.subunit_state("matrix_a", 1)["closed_count"] == 1


def test_routing_the_same_pair_twice_is_idempotent(armed):
    session, token = armed
    session.route(token, "scope_ch1", "dut_pin_a1")
    assert session.route(token, "dut_pin_a1", "scope_ch1")["status"] == "already_open"
    assert len(session.routes) == 1


def test_a_refused_route_leaves_the_fixture_untouched(armed):
    session, token = armed
    session.route(token, "psu_pos", "dut_pin_a1")
    before = session.subunit_state("matrix_a", 1)["closed"]
    with pytest.raises(InterlockError):
        session.route(token, "gnd", "dut_pin_a1")
    assert session.subunit_state("matrix_a", 1)["closed"] == before


def test_shared_crosspoints_are_reference_counted(armed):
    session, token = armed
    session.route(token, "dmm_hi", "rtd_1")
    session.route(token, "dmm_hi", "rtd_2")
    shared = Operation("matrix_a", 1, 6, 14)

    result = session.unroute(token, "dmm_hi", "rtd_1")
    assert result["retained_for_other_routes"] == [shared.as_dict()]
    assert session.backend.view_crosspoint("matrix_a", 1, 6, 14) is True

    session.unroute(token, "dmm_hi", "rtd_2")
    assert session.backend.view_crosspoint("matrix_a", 1, 6, 14) is False


def test_unrouting_something_that_was_never_routed_is_not_an_error(armed):
    session, token = armed
    assert session.unroute(token, "scope_ch1", "dut_pin_a3")["status"] == "not_open"


def test_a_partly_applied_route_is_rolled_back(armed, monkeypatch):
    """If the second crosspoint refuses, the first must not be left closed."""
    session, token = armed
    real = session.backend.close_crosspoint
    calls = {"n": 0}

    def flaky(alias, subunit, row, column):
        calls["n"] += 1
        if calls["n"] == 2:
            raise DriverError("simulated relay failure")
        return real(alias, subunit, row, column)

    monkeypatch.setattr(session.backend, "close_crosspoint", flaky)

    with pytest.raises(DriverError, match="simulated relay failure"):
        session.route(token, "dmm_hi", "tc_1")

    assert session.subunit_state("matrix_a", 1)["closed_count"] == 0
    assert session.routes == {}


def test_release_tears_the_fixture_down(armed):
    session, token = armed
    session.route(token, "scope_ch1", "dut_pin_a1")
    session.route(token, "dmm_hi", "tc_1")

    result = session.release(token)
    assert result["status"] == "released"
    assert len(result["routes_cleared"]) == 2
    assert session.subunit_state("matrix_a", 1)["closed_count"] == 0
    assert session.subunit_state("mux_b", 1)["closed_count"] == 0
    assert session.armed is False
    assert session.reservation is None


def test_direct_crosspoint_control_is_bounds_checked(armed):
    session, token = armed
    with pytest.raises(ValueError, match=r"outside 1\.\.8"):
        session.set_crosspoint(token, "matrix_a", 1, 99, 1, True)
    with pytest.raises(ValueError, match=r"outside 1\.\.16"):
        session.set_crosspoint(token, "matrix_a", 1, 1, 99, True)


def test_direct_control_will_not_undercut_a_route(armed):
    session, token = armed
    session.route(token, "scope_ch1", "dut_pin_a1")
    with pytest.raises(InterlockError, match="holding up route"):
        session.set_crosspoint(token, "matrix_a", 1, 4, 1, False)
    assert session.backend.view_crosspoint("matrix_a", 1, 4, 1) is True


def test_direct_control_still_answers_to_the_interlocks(armed):
    session, token = armed
    session.route(token, "psu_pos", "dut_pin_a1")
    with pytest.raises(InterlockError, match="electrically common"):
        session.set_crosspoint(token, "matrix_a", 1, 3, 1, True)


def test_plan_is_a_dry_run(session):
    plan = session.plan("scope_ch1", "dut_pin_a1")
    assert plan["permitted"] is False, "the interlock is not armed yet"
    assert "not armed" in plan["refusal"]
    assert session.subunit_state("matrix_a", 1)["closed_count"] == 0


def test_verify_topology_agrees_with_the_simulator(session):
    assert session.verify_topology() == {"ok": True, "problems": []}


def test_verify_topology_notices_a_rack_that_moved_on(bench):
    from pickering_lxi_mcp.driver import CardInfo, SimBackend, SubunitInfo

    shrunk = CardInfo(
        alias="matrix_a",
        bus=4,
        device=14,
        card_id="SIM-MATRIX-4x4",
        subunits=(SubunitInfo(1, "MATRIX", 4, 4, 4, 3000),),
    )
    session = ChassisSession.build(backend=SimBackend((shrunk,)), topology=bench)
    report = session.verify_topology()
    assert report["ok"] is False
    assert any("8x16" in p for p in report["problems"])
    assert any("mux_b" in p for p in report["problems"])


def test_the_journal_records_what_was_done(armed):
    session, token = armed
    session.route(token, "scope_ch1", "dut_pin_a1")
    session.unroute(token, "scope_ch1", "dut_pin_a1")
    assert any(entry.startswith("reserve") for entry in session.journal)
    assert any(entry.startswith("route") for entry in session.journal)
    assert any(entry.startswith("unroute") for entry in session.journal)

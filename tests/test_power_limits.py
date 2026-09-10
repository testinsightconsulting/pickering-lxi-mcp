"""Connectivity is not the only hazard.

On a DC fixture the dangerous state is a short — two things common that must not
be. On an RF fixture it is also magnitude: a source that can deliver more than a
destination survives, over a path nobody declared forbidden, because there is
nothing wrong with the path. Same graph, second predicate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pickering_lxi_mcp.errors import InterlockError
from pickering_lxi_mcp.interlocks import InterlockPolicy, overloads
from pickering_lxi_mcp.topology import Topology

BENCH = Path(__file__).resolve().parents[1] / "src" / "pickering_lxi_mcp" / "topologies"
CONFIRM = "the fixture is safe to energise"


def spec() -> dict:
    return json.loads((BENCH / "dut_bench.json").read_text())


def test_the_bench_declares_ratings(bench):
    assert bench.endpoint("awg_out").max_output_dbm == 20.0
    assert bench.endpoint("scope_ch1").max_input_dbm == 10.0
    assert bench.endpoint("dut_pin_a1").max_input_dbm is None, "most endpoints have no rating"


def test_ratings_survive_a_round_trip(bench):
    body = bench.endpoint("awg_out").as_dict()
    assert body["max_output_dbm"] == 20.0
    assert "max_input_dbm" not in body, "absent ratings stay absent rather than becoming null"


def test_nothing_is_flagged_on_an_idle_fixture(bench):
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    assert overloads(bench, policy, []) == []


def test_the_overload_is_a_composition_not_a_request(armed):
    """Each route is fine. The pair is not."""
    session, token = armed

    assert session.route(token, "awg_out", "dut_pin_a6")["status"] == "open"
    assert session.route(token, "scope_ch1", "dut_pin_a2")["status"] == "open"

    with pytest.raises(InterlockError, match="refused on power"):
        session.route(token, "scope_ch1", "dut_pin_a6")


def test_the_refusal_names_the_levels_and_the_margin(armed):
    session, token = armed
    session.route(token, "awg_out", "dut_pin_a6")
    with pytest.raises(InterlockError) as exc:
        session.route(token, "scope_ch1", "dut_pin_a6")
    message = str(exc.value)
    assert "+20.0 dBm" in message and "+10.0 dBm" in message
    assert "10.0 dB over" in message
    assert "The path is not forbidden — the level on it is" in message


def test_a_refused_overload_switches_nothing(armed):
    session, token = armed
    session.route(token, "awg_out", "dut_pin_a6")
    before = session.subunit_state("matrix_a", 1)["closed"]
    with pytest.raises(InterlockError):
        session.route(token, "scope_ch1", "dut_pin_a6")
    assert session.subunit_state("matrix_a", 1)["closed"] == before


def test_plan_reports_it_without_taking_the_chassis(armed):
    session, token = armed
    session.route(token, "awg_out", "dut_pin_a6")
    plan = session.plan("scope_ch2", "dut_pin_a6")
    assert plan["permitted"] is False
    assert "dBm" in plan["refusal"]


def test_the_same_generator_on_a_different_pin_is_fine(armed):
    session, token = armed
    session.route(token, "awg_out", "dut_pin_a6")
    assert session.route(token, "scope_ch1", "dut_pin_a2")["status"] == "open"


def test_an_unrated_destination_is_not_protected(armed):
    """Only a declared limit is enforced. Silence is not a rating."""
    session, token = armed
    session.route(token, "awg_out", "dut_pin_a6")
    assert session.route(token, "dmm_hi", "dut_pin_a6")["status"] == "open"


def test_the_check_can_be_turned_off_per_topology():
    body = spec()
    body["interlocks"]["enforce_power_limits"] = False
    topology = Topology(body)
    policy = InterlockPolicy.from_spec(topology.interlocks, topology)
    assert policy.enforce_power_limits is False

    from pickering_lxi_mcp.topology import Operation

    everything = [
        Operation(card.alias, sub.subunit, r, c)
        for card in topology.cards
        for sub in card.subunits
        for r in range(1, sub.rows + 1)
        for c in range(1, sub.columns + 1)
    ]
    assert overloads(topology, policy, everything) == []


def test_a_state_already_overloaded_is_reported_not_hidden(bench):
    """describe_violations covers it, so reconciliation sees it at startup too."""
    from pickering_lxi_mcp.interlocks import describe_violations
    from pickering_lxi_mcp.topology import Operation

    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    closed = {Operation("matrix_a", 1, 8, 6), Operation("matrix_a", 1, 4, 6)}
    problems = describe_violations(bench, policy, closed)
    assert any("dBm" in p for p in problems)


def test_an_overload_found_at_startup_cannot_be_adopted(session):
    """Adopting it would make the overload the baseline every later check allows."""
    from pickering_lxi_mcp.errors import ReconciliationError

    session.backend.close_crosspoint("matrix_a", 1, 8, 6)   # awg_out  -> a6
    session.backend.close_crosspoint("matrix_a", 1, 4, 6)   # scope_ch1 -> a6
    session.reconcile()
    assert session.reconciled is False

    token = session.reserve(owner="pytest").token
    with pytest.raises(ReconciliationError, match="breaks the topology's own rules"):
        session.adopt_existing_state(token, "adopt the state on the chassis")


def test_an_overload_already_present_does_not_block_unrelated_routes(armed):
    """A pre-existing problem must not become a reason to refuse everything."""
    session, token = armed
    session.route(token, "awg_out", "dut_pin_a6")
    session.unroute(token, "awg_out", "dut_pin_a6")
    assert session.route(token, "scope_ch1", "dut_pin_a6")["status"] == "open"
    assert session.route(token, "dmm_hi", "dut_pin_a3")["status"] == "open"

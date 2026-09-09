"""The interlocks, exercised as graph questions rather than as request filters."""

from __future__ import annotations

import pytest

from pickering_lxi_mcp.errors import InterlockError
from pickering_lxi_mcp.interlocks import InterlockPolicy, check_route, connectivity
from pickering_lxi_mcp.topology import Operation


def route_ops(topology, a, b):
    return topology.find_path(a, b).operations


def test_policy_comes_off_the_topology(bench):
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    assert policy.require_arm is True
    assert ("psu_pos", "gnd") in policy.forbidden_pairs
    assert "psu_pos" in policy.exclusive_endpoints
    assert policy.as_dict()["max_closures_per_subunit"] == 8


def test_a_policy_naming_an_endpoint_that_does_not_exist_is_refused(bench):
    with pytest.raises(Exception, match="unknown endpoint"):
        InterlockPolicy.from_spec({"forbidden_pairs": [["psu_pos", "ghost"]]}, bench)


def test_connectivity_follows_patch_leads_as_well_as_relays(bench):
    ops = route_ops(bench, "dmm_hi", "tc_1")
    components = connectivity(bench, ops)
    assert components.connected(
        bench.endpoint("dmm_hi").node, bench.endpoint("tc_1").node
    ), "a route makes its two endpoints common"


def test_nothing_is_common_before_anything_is_closed(bench):
    components = connectivity(bench, [])
    assert not components.connected(
        bench.endpoint("psu_pos").node, bench.endpoint("gnd").node
    )


def test_the_short_nobody_asked_for(bench):
    """Two individually reasonable routes that compose into a forbidden pair."""
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    already = set(route_ops(bench, "psu_pos", "dut_pin_a1"))

    with pytest.raises(InterlockError, match="electrically common"):
        check_route(
            bench,
            policy,
            closed=already,
            proposed=route_ops(bench, "gnd", "dut_pin_a1"),
            endpoints=("gnd", "dut_pin_a1"),
            armed=True,
            endpoints_in_use={},
        )


def test_the_same_route_is_fine_on_a_pin_the_supply_is_not_on(bench):
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    already = set(route_ops(bench, "psu_pos", "dut_pin_a1"))
    check_route(
        bench,
        policy,
        closed=already,
        proposed=route_ops(bench, "gnd", "dut_pin_a5"),
        endpoints=("gnd", "dut_pin_a5"),
        armed=True,
        endpoints_in_use={},
    )


def test_measuring_a_powered_pin_is_allowed(bench):
    """The interlock forbids specific pairs, not switching near a live supply."""
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    already = set(route_ops(bench, "psu_pos", "dut_pin_a1"))
    check_route(
        bench,
        policy,
        closed=already,
        proposed=route_ops(bench, "dmm_hi", "dut_pin_a1"),
        endpoints=("dmm_hi", "dut_pin_a1"),
        armed=True,
        endpoints_in_use={},
    )


def test_an_unarmed_chassis_refuses_before_it_looks_at_the_graph(bench):
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    with pytest.raises(InterlockError, match="not armed"):
        check_route(
            bench,
            policy,
            closed=set(),
            proposed=route_ops(bench, "scope_ch1", "dut_pin_a1"),
            endpoints=("scope_ch1", "dut_pin_a1"),
            armed=False,
            endpoints_in_use={},
        )


def test_an_exclusive_endpoint_takes_part_in_one_route_only(bench):
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    with pytest.raises(InterlockError, match="is exclusive"):
        check_route(
            bench,
            policy,
            closed=set(),
            proposed=route_ops(bench, "psu_pos", "dut_pin_a2"),
            endpoints=("psu_pos", "dut_pin_a2"),
            armed=True,
            endpoints_in_use={"psu_pos": "dut_pin_a1<->psu_pos"},
        )


def test_the_tighter_of_the_two_closure_limits_wins(bench):
    """Policy says 8 per subunit; the mux card itself says 1. One wins."""
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    already = {Operation("mux_b", 1, 1, 1)}
    with pytest.raises(InterlockError, match="over the limit of 1"):
        check_route(
            bench,
            policy,
            closed=already,
            proposed=(Operation("mux_b", 1, 1, 2),),
            endpoints=("scope_ch1", "tc_2"),
            armed=True,
            endpoints_in_use={},
        )


def test_the_policy_ceiling_bites_before_the_hardware_one(bench):
    policy = InterlockPolicy.from_spec(bench.interlocks, bench)
    closed = {Operation("matrix_a", 1, 1, c) for c in range(1, 9)}
    assert bench.subunit("matrix_a", 1).closure_limit == 12
    with pytest.raises(InterlockError, match="over the limit of 8"):
        check_route(
            bench,
            policy,
            closed=closed,
            proposed=(Operation("matrix_a", 1, 2, 9),),
            endpoints=("psu_neg", "dut_pin_a9"),
            armed=True,
            endpoints_in_use={},
        )

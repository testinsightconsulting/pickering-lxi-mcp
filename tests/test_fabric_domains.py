"""What can be leased separately, and what the hardware tree has to do with it.

Short answer to the second: nothing. A fabric domain is bounded below by the
subunit and unbounded above, and the boundary is decided by wiring rather than
by which box a card sits in. These tests pin all three directions of that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pickering_lxi_mcp.topology import Topology

BENCH = Path(__file__).resolve().parents[1] / "src" / "pickering_lxi_mcp" / "topologies"


def spec() -> dict:
    return json.loads((BENCH / "dut_bench.json").read_text())


def two_chassis(linked: bool) -> Topology:
    body = {
        "name": "two-chassis",
        "cards": {
            "chassis1_matrix": {
                "bus": 1, "device": 1,
                "subunits": [{"subunit": 1, "type": "MATRIX", "rows": 4, "columns": 4}],
            },
            "chassis2_matrix": {
                "bus": 9, "device": 1,
                "subunits": [{"subunit": 1, "type": "MATRIX", "rows": 4, "columns": 4}],
            },
        },
        "endpoints": {
            "a_src": {"card": "chassis1_matrix", "subunit": 1, "line": "row", "index": 1},
            "a_pin": {"card": "chassis1_matrix", "subunit": 1, "line": "column", "index": 1},
            "b_src": {"card": "chassis2_matrix", "subunit": 1, "line": "row", "index": 1},
            "b_pin": {"card": "chassis2_matrix", "subunit": 1, "line": "column", "index": 1},
        },
        "links": [],
    }
    if linked:
        body["links"] = [[
            {"card": "chassis1_matrix", "subunit": 1, "line": "column", "index": 4},
            {"card": "chassis2_matrix", "subunit": 1, "line": "row", "index": 4},
        ]]
    return Topology(body)


def test_the_shipped_bench_is_one_domain(bench):
    domains = bench.fabric_domains()
    assert len(domains) == 1
    assert domains[0].domain_id == "matrix_a/sub1"
    assert len(domains[0].endpoints) == 28
    assert domains[0].subunits == (("matrix_a", 1), ("mux_b", 1), ("mux_b", 2))


def test_one_card_can_host_two_domains():
    """Unpatched subunits on the same card are independently leasable."""
    body = spec()
    body["links"] = []
    domains = Topology(body).fabric_domains()

    assert len(domains) == 3
    mux = [d for d in domains if d.subunits[0][0] == "mux_b"]
    assert len(mux) == 2, "mux_b's two subunits are two separate domains"
    assert {d.domain_id for d in mux} == {"mux_b/sub1", "mux_b/sub2"}


def test_one_patch_lead_merges_two_chassis_into_one_domain():
    """And a domain can be larger than a chassis."""
    assert len(two_chassis(linked=False).fabric_domains()) == 2

    linked = two_chassis(linked=True)
    domains = linked.fabric_domains()
    assert len(domains) == 1
    assert set(domains[0].endpoints) == {"a_src", "a_pin", "b_src", "b_pin"}
    assert len(linked.find_path("a_src", "b_pin").operations) == 2


def test_a_subunit_is_never_split(bench):
    """The floor. Every row of a matrix reaches every column, so it is indivisible."""
    for links in ([], spec()["links"]):
        body = spec()
        body["links"] = links
        domains = Topology(body).fabric_domains()
        homes: dict[tuple[str, int], list[str]] = {}
        for domain in domains:
            for subunit in domain.subunits:
                homes.setdefault(subunit, []).append(domain.domain_id)
        for subunit, owners in homes.items():
            assert len(owners) == 1, f"{subunit} is split across domains {owners}"


def test_every_line_lands_in_exactly_one_domain(bench):
    domains = bench.fabric_domains()
    total = sum(d.line_count for d in domains)
    expected = sum(
        sub.rows + sub.columns for card in bench.cards for sub in card.subunits
    )
    assert total == expected
    assert len({d.domain_id for d in domains}) == len(domains)


def test_every_endpoint_lands_in_exactly_one_domain(bench):
    seen: list[str] = []
    for domain in bench.fabric_domains():
        seen.extend(domain.endpoints)
    assert sorted(seen) == sorted(bench.endpoints)


def test_a_lease_covers_whole_domains_not_the_endpoints_asked_for(bench):
    """Ask for one pin, be given the matrix. This is the operative constraint."""
    covering = bench.domains_for(["dut_pin_a1"])
    assert [d.domain_id for d in covering] == ["matrix_a/sub1"]
    assert len(covering[0].endpoints) == 28, "one pin drags in all 28 endpoints"


def test_domains_for_spans_everything_the_endpoints_touch():
    body = spec()
    body["links"] = []
    t = Topology(body)
    assert [d.domain_id for d in t.domains_for(["tc_1"])] == ["mux_b/sub1"]
    assert [d.domain_id for d in t.domains_for(["tc_1", "rtd_1"])] == [
        "mux_b/sub1",
        "mux_b/sub2",
    ]
    assert [d.domain_id for d in t.domains_for(["dut_pin_a1", "rtd_1"])] == [
        "matrix_a/sub1",
        "mux_b/sub2",
    ]


def test_domain_ids_are_stable_across_reloads(bench):
    first = [d.domain_id for d in bench.fabric_domains()]
    second = [d.domain_id for d in Topology.bundled("dut_bench").fabric_domains()]
    assert first == second


def test_domains_for_rejects_an_endpoint_that_does_not_exist(bench):
    from pickering_lxi_mcp.errors import TopologyError

    with pytest.raises(TopologyError, match="unknown endpoint"):
        bench.domains_for(["ghost_pin"])


def test_the_tool_reports_both_directions(session):
    from pickering_lxi_mcp import tools

    everything = tools.call(session, "list_fabric_domains")
    assert everything["domain_count"] == 1
    assert everything["domains"][0]["domain_id"] == "matrix_a/sub1"
    assert everything["requested_endpoints"] == []

    scoped = tools.call(session, "list_fabric_domains", for_endpoints=["dut_pin_a1"])
    assert scoped["requested_endpoints"] == ["dut_pin_a1"]
    assert [d["domain_id"] for d in scoped["domains"]] == ["matrix_a/sub1"]


def test_listing_domains_needs_no_reservation(session):
    """It is what you consult before deciding to take anything."""
    from pickering_lxi_mcp import tools

    session.reserve(owner="someone-else")
    assert tools.call(session, "list_fabric_domains")["domain_count"] == 1


def test_domains_are_independent_of_what_is_currently_closed(armed):
    """The question is what COULD become common, not what is."""
    session, token = armed
    before = session.topology.fabric_domains()
    session.route(token, "psu_pos", "dut_pin_a1")
    session.route(token, "dmm_hi", "tc_1")
    assert session.topology.fabric_domains() == before


# --------------------------------------------------------------------------
# Safety is domain-local, which is what makes ownership granularity a policy
# choice rather than a forced one -- and what makes a cross-domain safety rule
# a bug rather than a precaution.
# --------------------------------------------------------------------------


def test_a_route_never_crosses_a_domain_boundary():
    """By construction: two endpoints are routable only if they can become common."""
    from pickering_lxi_mcp.errors import PathError

    body = spec()
    body["links"] = []
    t = Topology(body)
    home = {n: d.domain_id for d in t.fabric_domains() for n in d.endpoints}

    assert home["dmm_hi"] != home["tc_1"]
    with pytest.raises(PathError, match="no switch path"):
        t.find_path("dmm_hi", "tc_1")

    assert home["dmm_hi"] == home["dut_pin_a1"]
    assert t.find_path("dmm_hi", "dut_pin_a1").operations


def test_a_forbidden_pair_across_domains_can_never_fire():
    """Close every crosspoint on the chassis; they still do not meet."""
    from pickering_lxi_mcp.interlocks import InterlockPolicy, connectivity
    from pickering_lxi_mcp.topology import Operation

    body = spec()
    body["links"] = []
    t = Topology(body)
    policy = InterlockPolicy.from_spec(body["interlocks"], t)

    everything = [
        Operation(card.alias, sub.subunit, row, column)
        for card in t.cards
        for sub in card.subunits
        for row in range(1, sub.rows + 1)
        for column in range(1, sub.columns + 1)
    ]
    components = connectivity(t, everything)

    for a, b in policy.forbidden_pairs:
        home_a = next(d.domain_id for d in t.fabric_domains() if a in d.endpoints)
        home_b = next(d.domain_id for d in t.fabric_domains() if b in d.endpoints)
        common = components.connected(t.endpoint(a).node, t.endpoint(b).node)
        assert common == (home_a == home_b), (
            "two endpoints can become common exactly when they share a domain"
        )


def make_session(topology):
    from pickering_lxi_mcp.driver import SimBackend
    from pickering_lxi_mcp.session import ChassisSession

    return ChassisSession.build(backend=SimBackend(topology.cards), topology=topology)


def test_the_shipped_topology_declares_no_vacuous_rules(session):
    assert session.verify_topology() == {"ok": True, "problems": []}


def test_a_rule_that_can_never_fire_is_reported():
    """The realistic cause is a patch lead in the rack that is not in the file."""
    body = spec()
    body["endpoints"]["gnd"] = {
        "card": "mux_b", "subunit": 2, "line": "column", "index": 8, "role": "ground",
    }
    body["links"] = [body["links"][0]]  # the lead that would tie them is gone

    report = make_session(Topology(body)).verify_topology()
    assert report["ok"] is False
    problem = next(p for p in report["problems"] if "can never fire" in p)
    assert "'psu_pos'/'gnd'" in problem
    assert "matrix_a/sub1" in problem and "mux_b/sub2" in problem
    assert "patch lead" in problem


def test_a_rule_naming_endpoints_that_cannot_meet_is_reported():
    body = spec()
    body["links"] = []
    body["interlocks"]["forbidden_pairs"] = [["psu_pos", "tc_1"]]
    report = make_session(Topology(body)).verify_topology()
    assert report["ok"] is False
    assert any("can never fire" in p for p in report["problems"])


def test_a_rule_inside_one_domain_is_not_reported():
    body = spec()
    body["links"] = []
    body["interlocks"]["forbidden_pairs"] = [["psu_pos", "gnd"]]
    report = make_session(Topology(body)).verify_topology()
    assert [p for p in report["problems"] if "can never fire" in p] == []


# --------------------------------------------------------------------------
# A DUT that joins two of its own pins is not discoverable and IS declarable.
# Declared, it is enforced like any other link; undeclared, verify_topology is
# what notices, because the rule it disarms becomes unreachable.
# --------------------------------------------------------------------------


def two_halves(bridge: bool) -> Topology:
    """Two matrices, no patch lead. The only thing that can join them is the DUT."""
    body = {
        "name": "two-halves",
        "cards": {
            "m1": {"bus": 1, "device": 1,
                   "subunits": [{"subunit": 1, "type": "MATRIX", "rows": 3, "columns": 4}]},
            "m2": {"bus": 1, "device": 2,
                   "subunits": [{"subunit": 1, "type": "MATRIX", "rows": 3, "columns": 4}]},
        },
        "endpoints": {
            "psu_pos": {"card": "m1", "subunit": 1, "line": "row", "index": 1},
            "dut_in": {"card": "m1", "subunit": 1, "line": "column", "index": 1},
            "gnd": {"card": "m2", "subunit": 1, "line": "row", "index": 1},
            "dut_out": {"card": "m2", "subunit": 1, "line": "column", "index": 1},
        },
        "links": [],
        "interlocks": {"require_arm": False, "forbidden_pairs": [["psu_pos", "gnd"]]},
    }
    if bridge:
        body["links"] = [[
            {"card": "m1", "subunit": 1, "line": "column", "index": 1},
            {"card": "m2", "subunit": 1, "line": "column", "index": 1},
        ]]
    return Topology(body)


def test_a_declared_dut_bridge_merges_the_domains_and_is_enforced():
    topology = two_halves(bridge=True)
    assert len(topology.fabric_domains()) == 1, "the bridge makes the two halves one fabric"

    session = make_session(topology)
    assert session.verify_topology()["ok"] is True

    token = session.reserve(owner="pytest").token
    session.route(token, "psu_pos", "dut_in")

    from pickering_lxi_mcp.errors import InterlockError

    with pytest.raises(InterlockError, match="electrically common"):
        session.route(token, "gnd", "dut_out")


def test_an_undeclared_dut_bridge_is_not_enforceable_and_verify_says_so():
    """The hazard, and the only warning available: the rule it disarms is unreachable."""
    topology = two_halves(bridge=False)
    assert len(topology.fabric_domains()) == 2

    session = make_session(topology)
    report = session.verify_topology()
    assert report["ok"] is False
    assert any("can never fire" in p for p in report["problems"])

    token = session.reserve(owner="pytest").token
    session.route(token, "psu_pos", "dut_in")
    # Nothing refuses this, because nothing in the file says the DUT joins the halves.
    assert session.route(token, "gnd", "dut_out")["status"] == "open"


def test_declaring_a_bridge_is_the_conservative_direction():
    """A DUT whose internal path is conditional should still be declared.

    Declaring over-connects the graph, so the interlock refuses more than it
    strictly must. Over-refusing is the failure direction you want.
    """
    declared = make_session(two_halves(bridge=True))
    token = declared.reserve(owner="pytest").token
    declared.route(token, "psu_pos", "dut_in")

    plan = declared.plan("gnd", "dut_out")
    assert plan["permitted"] is False
    assert "electrically common" in plan["refusal"]

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

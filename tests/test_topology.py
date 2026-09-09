"""The map, and the search over it."""

from __future__ import annotations

import json

import pytest

from pickering_lxi_mcp.errors import PathError, TopologyError
from pickering_lxi_mcp.topology import Topology


def test_bundled_topology_loads_and_describes_itself(bench):
    assert bench.name == "dut-bench"
    assert {c.alias for c in bench.cards} == {"matrix_a", "mux_b"}
    assert "psu_pos" in bench.endpoints
    assert bench.as_dict()["interlocks"]["require_arm"] is True


def test_a_matrix_crosspoint_is_one_hop(bench):
    path = bench.find_path("scope_ch1", "dut_pin_a1")
    assert [op.as_dict() for op in path.operations] == [
        {"card": "matrix_a", "subunit": 1, "row": 4, "column": 1}
    ]


def test_routing_is_undirected(bench):
    there = bench.find_path("scope_ch1", "dut_pin_a1")
    back = bench.find_path("dut_pin_a1", "scope_ch1")
    assert set(there.operations) == set(back.operations)


def test_a_patch_lead_is_traversed_but_never_switched(bench):
    path = bench.find_path("dmm_hi", "tc_1")
    assert len(path.operations) == 2, "one matrix crosspoint plus one mux channel"
    assert {op.card for op in path.operations} == {"matrix_a", "mux_b"}
    assert path.nodes[1] == ("matrix_a", 1, "column", 13), "the patched column is on the path"


def test_search_returns_the_fewest_closures(bench):
    # scope_ch1 and scope_ch2 are both rows: reaching one from the other means
    # bussing through a shared column, which is two closures and not three.
    path = bench.find_path("scope_ch1", "scope_ch2")
    assert len(path.operations) == 2


def test_unreachable_endpoints_raise_path_error(islands):
    with pytest.raises(PathError, match="no switch path"):
        islands.find_path("a", "far")


def test_two_names_for_one_line_are_already_common(islands):
    with pytest.raises(PathError, match="same physical line"):
        islands.find_path("b", "b_too")


def test_unknown_endpoint_names_the_ones_that_exist(bench):
    with pytest.raises(TopologyError, match="unknown endpoint"):
        bench.find_path("scope_ch1", "no_such_pin")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"cards": {}}, "non-empty 'cards'"),
        ({"endpoints": {}}, "non-empty 'endpoints'"),
    ],
)
def test_structurally_empty_topologies_are_refused(mutation, message):
    spec = {
        "name": "x",
        "cards": {"c": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 1, "columns": 1}]}},
        "endpoints": {"e": {"card": "c", "subunit": 1, "line": "row", "index": 1}},
    }
    spec.update(mutation)
    with pytest.raises(TopologyError, match=message):
        Topology(spec)


def test_an_endpoint_off_the_end_of_the_matrix_is_refused():
    spec = {
        "name": "x",
        "cards": {"c": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 2, "columns": 2}]}},
        "endpoints": {"e": {"card": "c", "subunit": 1, "line": "column", "index": 9}},
    }
    with pytest.raises(TopologyError, match=r"outside 1\.\.2"):
        Topology(spec)


def test_a_link_to_a_card_that_is_not_there_is_refused():
    spec = {
        "name": "x",
        "cards": {"c": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 2, "columns": 2}]}},
        "endpoints": {"e": {"card": "c", "subunit": 1, "line": "row", "index": 1}},
        "links": [
            [
                {"card": "c", "subunit": 1, "line": "column", "index": 1},
                {"card": "ghost", "subunit": 1, "line": "row", "index": 1},
            ]
        ],
    }
    with pytest.raises(TopologyError, match="unknown card 'ghost'"):
        Topology(spec)


def test_a_malformed_file_says_which_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    with pytest.raises(TopologyError, match="not valid JSON"):
        Topology.load(bad)
    with pytest.raises(TopologyError, match="no topology file at"):
        Topology.load(tmp_path / "absent.json")


def test_every_bundled_topology_is_loadable():
    names = Topology.bundled_names()
    assert names, "the package ships at least one example topology"
    for name in names:
        assert Topology.bundled(name).endpoints


def test_as_dict_round_trips_through_json(bench):
    assert json.loads(json.dumps(bench.as_dict()))["name"] == "dut-bench"

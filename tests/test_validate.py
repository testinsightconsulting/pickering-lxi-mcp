"""The file-only checks: what can be decided before the rack exists."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pickering_lxi_mcp import validate
from pickering_lxi_mcp.topology import Topology

BENCH = Path(__file__).resolve().parents[1] / "src" / "pickering_lxi_mcp" / "topologies"


def problems_for(body: dict) -> tuple[list[str], list[str], list[str]]:
    return validate.check(Topology(body))


def minimal() -> dict:
    return {
        "name": "t",
        "cards": {
            "m1": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 2, "columns": 2}]},
            "m2": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 2, "columns": 2}]},
        },
        "endpoints": {
            "src": {"card": "m1", "subunit": 1, "line": "row", "index": 1, "role": "source"},
            "pin": {"card": "m1", "subunit": 1, "line": "column", "index": 1, "role": "dut"},
            "far": {"card": "m2", "subunit": 1, "line": "row", "index": 1, "role": "ground"},
        },
        "links": [],
        "interlocks": {},
    }


# -- the shipped examples --------------------------------------------------


@pytest.mark.parametrize("name", ["dut_bench", "rf_bench"])
def test_every_shipped_topology_has_no_problems(name):
    problems, _warnings, _notes = validate.check(Topology.bundled(name))
    assert problems == []


def test_the_rf_bench_is_fully_rated():
    """The worked example should not be teaching people to ship warnings."""
    _problems, warnings, _notes = validate.check(Topology.bundled("rf_bench"))
    assert warnings == []


def test_the_rf_bench_reports_the_overloads_it_will_refuse():
    _p, _w, notes = validate.check(Topology.bundled("rf_bench"))
    joined = " ".join(notes)
    assert "sig_gen_out (+26.0 dBm) can reach dut_rx_direct (+10.0 dBm) — 16.0 dB over" in joined
    assert "2 fabric domain(s)" in joined


# -- the checks themselves -------------------------------------------------


def test_a_closure_limit_larger_than_the_subunit_is_a_problem():
    body = minimal()
    body["cards"]["m1"]["subunits"][0]["closure_limit"] = 99
    problems, _w, _n = problems_for(body)
    assert any("closure limit 99 exceeds" in p for p in problems)


def test_a_rule_that_can_never_fire_is_a_problem():
    body = minimal()
    body["interlocks"]["forbidden_pairs"] = [["src", "far"]]
    problems, _w, _n = problems_for(body)
    assert any("can never fire" in p for p in problems)


def test_a_malformed_policy_is_reported_rather_than_raised():
    body = minimal()
    body["interlocks"]["exclusive_endpoints"] = ["ghost"]
    problems, _w, _n = problems_for(body)
    assert any("interlock policy is malformed" in p for p in problems)
    assert any("ghost" in p for p in problems)


def test_two_names_on_one_line_are_flagged():
    body = minimal()
    body["endpoints"]["alias"] = {
        "card": "m1", "subunit": 1, "line": "row", "index": 1, "role": "source",
    }
    _p, warnings, _n = problems_for(body)
    assert any("share one line" in w for w in warnings)


def test_an_unrated_destination_under_a_rated_source_is_warned():
    body = minimal()
    body["endpoints"]["src"]["max_output_dbm"] = 30
    _p, warnings, _n = problems_for(body)
    assert any("declare no max_input_dbm" in w and "pin" in w for w in warnings)


def test_the_unrated_warning_is_one_line_per_source_not_per_destination():
    """Twenty identical warnings bury every other finding."""
    body = minimal()
    body["endpoints"]["src"]["max_output_dbm"] = 30
    for i in range(1, 3):
        body["endpoints"][f"extra{i}"] = {
            "card": "m1", "subunit": 1, "line": "column", "index": i, "role": "dut",
        }
    _p, warnings, _n = problems_for(body)
    unrated = [w for w in warnings if "max_input_dbm" in w]
    assert len(unrated) == 1
    assert "destination(s)" in unrated[0]


def test_enforcement_on_with_nothing_to_enforce_is_warned():
    body = minimal()
    body["interlocks"]["enforce_power_limits"] = True
    _p, warnings, _n = problems_for(body)
    assert any("can never fire" in w for w in warnings)


# -- the command line ------------------------------------------------------


def test_the_cli_passes_the_shipped_topologies(capsys):
    assert validate.main([str(BENCH)]) == 0
    out = capsys.readouterr().out
    assert "rf-bench" in out and "dut-bench" in out


def test_the_cli_fails_on_a_broken_file(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    body = minimal()
    body["cards"]["m1"]["subunits"][0]["closure_limit"] = 99
    bad.write_text(json.dumps(body))
    assert validate.main([str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_cli_reports_an_unparseable_file_rather_than_raising(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert validate.main([str(bad)]) == 1
    assert "PROBLEM" in capsys.readouterr().out


def test_the_cli_explains_itself(capsys):
    assert validate.main([]) == 1
    assert "usage:" in capsys.readouterr().out
    assert validate.main(["--help"]) == 0


def test_the_cli_reports_an_empty_directory(tmp_path, capsys):
    assert validate.main([str(tmp_path)]) == 1
    assert "no topology files found" in capsys.readouterr().out

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pickering_lxi_mcp.driver import SimBackend
from pickering_lxi_mcp.session import ChassisSession
from pickering_lxi_mcp.topology import Topology

BENCH = Path(__file__).resolve().parents[1] / "src" / "pickering_lxi_mcp" / "topologies"


def make_session(topology: Topology) -> ChassisSession:
    return ChassisSession.build(backend=SimBackend(topology.cards), topology=topology)


@pytest.fixture
def bench() -> Topology:
    return Topology.bundled("dut_bench")


@pytest.fixture
def session(bench: Topology) -> ChassisSession:
    return make_session(bench)


@pytest.fixture
def armed(session: ChassisSession) -> tuple[ChassisSession, str]:
    token = session.reserve(owner="pytest").token
    session.arm(token, "the fixture is safe to energise")
    return session, token


ISLANDS: dict[str, Any] = {
    "name": "islands",
    "cards": {
        "left": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 2, "columns": 2}]},
        "right": {"subunits": [{"subunit": 1, "type": "MATRIX", "rows": 2, "columns": 2}]},
    },
    "endpoints": {
        "a": {"card": "left", "subunit": 1, "line": "row", "index": 1},
        "b": {"card": "left", "subunit": 1, "line": "column", "index": 1},
        "b_too": {"card": "left", "subunit": 1, "line": "column", "index": 1},
        "far": {"card": "right", "subunit": 1, "line": "column", "index": 2},
    },
    "interlocks": {"require_arm": False},
}


@pytest.fixture
def islands() -> Topology:
    return Topology(json.loads(json.dumps(ISLANDS)), source="<islands>")

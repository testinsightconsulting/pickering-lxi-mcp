"""How a session gets built, in one place.

The MCP server, the walkthrough runner and the tests all come through here, so
"what does this server do when you just run it" has exactly one answer:
simulator, bundled topology, nothing reached for over the network.
"""

from __future__ import annotations

import os
from pathlib import Path

from .driver import build_backend
from .session import ChassisSession
from .topology import Topology

DEFAULT_TOPOLOGY = "dut_bench"


def load_topology(env: dict[str, str] | None = None) -> Topology:
    env = dict(os.environ if env is None else env)
    path = env.get("PICKERING_LXI_TOPOLOGY", "").strip()
    if path:
        return Topology.load(Path(path))
    return Topology.bundled(DEFAULT_TOPOLOGY)


def build_session(env: dict[str, str] | None = None) -> ChassisSession:
    env = dict(os.environ if env is None else env)
    topology = load_topology(env)
    backend = build_backend(topology.cards, env=env)
    return ChassisSession.build(backend=backend, topology=topology)

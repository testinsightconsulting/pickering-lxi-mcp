"""How a session gets built, in one place.

The MCP server, the walkthrough runner and the tests all come through here, so
"what does this server do when you just run it" has exactly one answer:
simulator, bundled topology, nothing reached for over the network.
"""

from __future__ import annotations

import os
from pathlib import Path

from .driver import build_backend
from .errors import TopologyError
from .session import ChassisSession
from .topology import Topology

DEFAULT_TOPOLOGY = "dut_bench"


def load_topology(env: dict[str, str] | None = None) -> Topology:
    """PICKERING_LXI_TOPOLOGY is a path, or the name of a bundled bench.

    More than one bench ships in the package, and making somebody dig the
    install directory out of ``pip show`` to point at one of them is a bad
    answer. A value that names a bundled topology resolves to it; anything
    else is treated as a path, and a path that does not exist says so and
    lists the names that would have worked.
    """

    env = dict(os.environ if env is None else env)
    value = env.get("PICKERING_LXI_TOPOLOGY", "").strip()
    if not value:
        return Topology.bundled(DEFAULT_TOPOLOGY)

    bundled = Topology.bundled_names()
    if value in bundled:
        return Topology.bundled(value)
    if not Path(value).is_file():
        raise TopologyError(
            f"PICKERING_LXI_TOPOLOGY={value!r} is neither a file nor a bundled topology. "
            f"Bundled: {', '.join(bundled)}."
        )
    return Topology.load(Path(value))


def build_session(env: dict[str, str] | None = None) -> ChassisSession:
    env = dict(os.environ if env is None else env)
    topology = load_topology(env)
    backend = build_backend(topology.cards, env=env)
    return ChassisSession.build(backend=backend, topology=topology)

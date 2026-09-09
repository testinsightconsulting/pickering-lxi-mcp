"""MCP server exposing the tiered switching tools over stdio.

Run against the simulator (default) or a real chassis:

    pickering-lxi-mcp                                       # in-process simulator
    PICKERING_LXI_ADDRESS=192.168.1.50 pickering-lxi-mcp    # LXI chassis by IP
    PICKERING_LXI_ADDRESS=PXI pickering-lxi-mcp             # local PXI cards
    PICKERING_LXI_SIM_CARD=1 PICKERING_LXI_ADDRESS=PXI \
        pickering-lxi-mcp                                   # vendor driver, simulated cards
    PICKERING_LXI_TOPOLOGY=./my_bench.json pickering-lxi-mcp

The tool bodies are one-liners on purpose. All behaviour lives in
``tools.call``, so the MCP binding and the CI walkthroughs exercise exactly the
same dispatch path -- a walkthrough that passes is evidence about the server,
not about a parallel test-only implementation.
"""

from __future__ import annotations

from typing import Any

try:  # mcp >= 2.0 renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from . import __version__, tools
from .errors import PickeringError
from .factory import build_session

INSTRUCTIONS = """\
Switching for a multi-vendor test rack: connect two named endpoints, and refuse
the connections that would damage the fixture.

Work in this order.

1. list_endpoints, and plan_route for the connection you want. plan_route is a
   dry run -- it switches nothing, needs no reservation, and tells you both the
   crosspoints involved and whether the interlocks would permit it. Ask it
   first; a refusal here costs nothing.
2. reserve_chassis to take the chassis, then arm_interlock with
   confirm="the fixture is safe to energise". Both are required before any
   relay moves.
3. route_signal / unroute_signal by endpoint name. A route is applied whole or
   not at all, and unroute keeps crosspoints that other routes still need.
4. release_chassis when you are done. It clears every route and disarms, so a
   run that ends unexpectedly does not leave the fixture live.

Observation -- list_cards, list_routes, subunit_state, crosspoint_state,
interlock_status, plan_route -- is never gated. Read freely, including a
chassis someone else has reserved.

A refusal from this server is information, not an obstacle. An InterlockError
naming two endpoints as "electrically common" means the route you asked for
would compose with routes already open into a connection the topology forbids;
the fix is a different pin or tearing down the conflicting route, never a
retry. Nothing is switched when a route is refused.
"""

_KWARGS = {"instructions": INSTRUCTIONS}
try:
    server = _Server("pickering-lxi", version=__version__, **_KWARGS)
except TypeError:  # pragma: no cover - mcp 1.x has no version parameter
    server = _Server("pickering-lxi", **_KWARGS)

SESSION = build_session()


# A refusal from this server is information the model needs, so it must reach
# the model. The SDK deliberately withholds the text of an unexpected exception
# and shows only "Error executing tool <name>"; ToolError is the channel for a
# failure the server anticipated. Everything this server raises on purpose --
# an interlock, a missing reservation, an unknown endpoint, an out-of-range
# coordinate -- is anticipated, and is translated here. Anything else is a bug
# and is allowed to crash loudly rather than be dressed up as a refusal.
ANTICIPATED = (PickeringError, PermissionError, ValueError, KeyError)


def _call(name: str, **kwargs: Any) -> Any:
    """The one place the MCP binding touches the tool layer."""
    try:
        return tools.call(SESSION, name, **kwargs)
    except ANTICIPATED as exc:
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc

# -- OBSERVE tier ----------------------------------------------------------


@server.tool()
def chassis_identify() -> dict[str, Any]:
    """Backend, driver, topology and current chassis status."""
    return _call("chassis_identify")


@server.tool()
def list_cards() -> dict[str, Any]:
    """Every open card with its subunits, matrix sizes and closure limits."""
    return _call("list_cards")


@server.tool()
def subunit_state(card: str, subunit: int) -> dict[str, Any]:
    """Every closed crosspoint on one subunit."""
    return _call("subunit_state", card=card, subunit=subunit)


@server.tool()
def crosspoint_state(card: str, subunit: int, row: int, column: int) -> dict[str, Any]:
    """Whether one crosspoint is closed, and which routes are holding it."""
    return _call("crosspoint_state", card=card, subunit=subunit, row=row, column=column)


@server.tool()
def list_endpoints() -> dict[str, Any]:
    """The logical endpoint names this topology can route between."""
    return _call("list_endpoints")


@server.tool()
def list_routes() -> dict[str, Any]:
    """Logical connections currently held open by this server."""
    return _call("list_routes")


@server.tool()
def plan_route(from_endpoint: str, to_endpoint: str) -> dict[str, Any]:
    """Dry run a route: the crosspoints it would close, and whether the interlocks permit it.

    Nothing is switched. Ask this before reserving the chassis.
    """
    return _call("plan_route", from_endpoint=from_endpoint, to_endpoint=to_endpoint)


@server.tool()
def interlock_status() -> dict[str, Any]:
    """Whether the interlock is armed, and the safety policy in force."""
    return _call("interlock_status")


@server.tool()
def verify_topology() -> dict[str, Any]:
    """Check the topology's claims about the rack against what the chassis reports."""
    return _call("verify_topology")


@server.tool()
def reserve_chassis(owner: str, ttl_seconds: float = 900.0) -> dict[str, Any]:
    """Take a time-boxed reservation. Returns the token every mutating tool requires."""
    return _call("reserve_chassis", owner=owner, ttl_seconds=ttl_seconds)


@server.tool()
def list_tool_tiers() -> list[dict[str, str]]:
    """List every tool with its tier, so an agent can plan before it reserves."""
    return tools.manifest()


# -- MUTATE tier -----------------------------------------------------------


@server.tool()
def arm_interlock(token: str, confirm: str) -> dict[str, Any]:
    """Arm the chassis interlock. `confirm` must be exactly 'the fixture is safe to energise'."""
    return _call("arm_interlock", token=token, confirm=confirm)


@server.tool()
def disarm_interlock(token: str) -> dict[str, Any]:
    """Disarm the interlock. Routes already open stay up; no new ones can be made."""
    return _call("disarm_interlock", token=token)


@server.tool()
def route_signal(token: str, from_endpoint: str, to_endpoint: str) -> dict[str, Any]:
    """Connect two logical endpoints by the shortest switch path. Refused whole if unsafe."""
    return _call(
        "route_signal", token=token, from_endpoint=from_endpoint, to_endpoint=to_endpoint
    )


@server.tool()
def unroute_signal(token: str, from_endpoint: str, to_endpoint: str) -> dict[str, Any]:
    """Tear down one route, keeping any crosspoints other routes still need."""
    return _call(
        "unroute_signal", token=token, from_endpoint=from_endpoint, to_endpoint=to_endpoint
    )


@server.tool()
def clear_all_routes(token: str) -> dict[str, Any]:
    """Open every crosspoint on every card and forget all routes."""
    return _call("clear_all_routes", token=token)


@server.tool()
def set_crosspoint(
    token: str, card: str, subunit: int, row: int, column: int, state: bool
) -> dict[str, Any]:
    """Operate one crosspoint directly. Still bounds-checked and interlock-checked."""
    return _call(
        "set_crosspoint",
        token=token,
        card=card,
        subunit=subunit,
        row=row,
        column=column,
        state=state,
    )


@server.tool()
def release_chassis(token: str) -> dict[str, Any]:
    """Clear every route, disarm the interlock, and release the reservation."""
    return _call("release_chassis", token=token)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()

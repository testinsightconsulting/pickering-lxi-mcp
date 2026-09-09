"""Typed tool surface, split into two tiers.

Tier separation is structural, not documentary. Every callable registered here
declares its tier, and the dispatcher refuses to run a MUTATE tool without a
reservation token. There is no ``op_crosspoint(card, sub, row, col)`` escape
hatch onto the vendor driver: an agent cannot reach a relay except through a
tool whose arguments are typed, whose bounds are checked against what the card
actually reports, and whose effect on the fixture's connectivity graph is
checked before anything moves.

``call`` is the only dispatch point in the process. The MCP server, the tests
and the CI walkthroughs all go through it, so a green walkthrough is evidence
about the server rather than about a parallel test-only implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .session import ChassisSession


class Tier(str, Enum):
    OBSERVE = "observe"
    MUTATE = "mutate"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tier: Tier
    summary: str
    handler: Callable[..., Any]


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, tier: Tier, summary: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY[name] = ToolSpec(name=name, tier=tier, summary=summary, handler=fn)
        return fn

    return register


# --------------------------------------------------------------------------
# OBSERVE tier - safe on any chassis at any time, including one another
# engineer has reserved. Read-only by construction.
# --------------------------------------------------------------------------


@tool("chassis_identify", Tier.OBSERVE, "Backend, driver, topology and current chassis status.")
def chassis_identify(session: ChassisSession) -> dict[str, Any]:
    return session.describe()


@tool("list_cards", Tier.OBSERVE, "Every open card with its subunits, sizes and closure limits.")
def list_cards(session: ChassisSession) -> dict[str, Any]:
    return {"cards": session.list_cards()}


@tool("subunit_state", Tier.OBSERVE, "Every closed crosspoint on one subunit.")
def subunit_state(session: ChassisSession, card: str, subunit: int) -> dict[str, Any]:
    return session.subunit_state(card, subunit)


@tool("crosspoint_state", Tier.OBSERVE, "Whether one crosspoint is closed, and which routes hold it.")
def crosspoint_state(
    session: ChassisSession, card: str, subunit: int, row: int, column: int
) -> dict[str, Any]:
    return session.crosspoint(card, subunit, row, column)


@tool("list_endpoints", Tier.OBSERVE, "The logical endpoint names this topology can route between.")
def list_endpoints(session: ChassisSession) -> dict[str, Any]:
    return {"topology": session.topology.name, "endpoints": session.list_endpoints()}


@tool("list_fabric_domains", Tier.OBSERVE, "The independently leasable units of this fixture, and what a lease over given endpoints must cover.")
def list_fabric_domains(
    session: ChassisSession, for_endpoints: list[str] | None = None
) -> dict[str, Any]:
    return session.fabric_domains(for_endpoints)


@tool("list_routes", Tier.OBSERVE, "Logical connections currently held open by this server.")
def list_routes(session: ChassisSession) -> dict[str, Any]:
    return {"routes": session.list_routes()}


@tool("plan_route", Tier.OBSERVE, "Dry run: the crosspoints a route would close, and whether the interlocks permit it.")
def plan_route(session: ChassisSession, from_endpoint: str, to_endpoint: str) -> dict[str, Any]:
    return session.plan(from_endpoint, to_endpoint)


@tool("reconciliation_status", Tier.OBSERVE, "What was found already closed at startup, and what it breaks.")
def reconciliation_status(session: ChassisSession) -> dict[str, Any]:
    return session.reconciliation_status()


@tool("interlock_status", Tier.OBSERVE, "Whether the interlock is armed, and the policy in force.")
def interlock_status(session: ChassisSession) -> dict[str, Any]:
    return session.interlock_status()


@tool("verify_topology", Tier.OBSERVE, "Check the topology's claims against what the chassis reports.")
def verify_topology(session: ChassisSession) -> dict[str, Any]:
    return session.verify_topology()


@tool("reserve_chassis", Tier.OBSERVE, "Take a time-boxed reservation; returns the token every mutating tool needs.")
def reserve_chassis(
    session: ChassisSession, owner: str, ttl_seconds: float = 900.0
) -> dict[str, Any]:
    res = session.reserve(owner=owner, ttl_seconds=ttl_seconds)
    return {"token": res.token, "owner": res.owner, "ttl_seconds": ttl_seconds}


# --------------------------------------------------------------------------
# MUTATE tier - moves relays. Requires a reservation token, and everything
# except arming also requires the interlock to be armed.
# --------------------------------------------------------------------------


@tool("adopt_existing_state", Tier.MUTATE, "Keep crosspoints found closed at startup and count them in every later check.")
def adopt_existing_state(session: ChassisSession, token: str, confirm: str) -> dict[str, Any]:
    return session.adopt_existing_state(token, confirm)


@tool("clear_existing_state", Tier.MUTATE, "Open every crosspoint found closed at startup and begin from a known chassis.")
def clear_existing_state(session: ChassisSession, token: str, confirm: str) -> dict[str, Any]:
    return session.clear_existing_state(token, confirm)


@tool("arm_interlock", Tier.MUTATE, "Arm the chassis interlock with an explicit acknowledgement.")
def arm_interlock(session: ChassisSession, token: str, confirm: str) -> dict[str, Any]:
    return session.arm(token, confirm)


@tool("disarm_interlock", Tier.MUTATE, "Disarm the interlock. Existing routes stay up.")
def disarm_interlock(session: ChassisSession, token: str) -> dict[str, Any]:
    return session.disarm(token)


@tool("route_signal", Tier.MUTATE, "Connect two logical endpoints by the shortest switch path.")
def route_signal(
    session: ChassisSession, token: str, from_endpoint: str, to_endpoint: str
) -> dict[str, Any]:
    return session.route(token, from_endpoint, to_endpoint)


@tool("unroute_signal", Tier.MUTATE, "Tear down one route, keeping crosspoints other routes still need.")
def unroute_signal(
    session: ChassisSession, token: str, from_endpoint: str, to_endpoint: str
) -> dict[str, Any]:
    return session.unroute(token, from_endpoint, to_endpoint)


@tool("clear_all_routes", Tier.MUTATE, "Open every crosspoint on every card and forget all routes.")
def clear_all_routes(session: ChassisSession, token: str) -> dict[str, Any]:
    return session.clear_all_routes(token)


@tool("set_crosspoint", Tier.MUTATE, "Operate one crosspoint directly, still bounds- and interlock-checked.")
def set_crosspoint(
    session: ChassisSession,
    token: str,
    card: str,
    subunit: int,
    row: int,
    column: int,
    state: bool,
) -> dict[str, Any]:
    return session.set_crosspoint(token, card, subunit, row, column, state)


@tool("release_chassis", Tier.MUTATE, "Clear every route, disarm, and release the reservation.")
def release_chassis(session: ChassisSession, token: str) -> dict[str, Any]:
    return session.release(token)


def call(session: ChassisSession, name: str, **kwargs: Any) -> Any:
    """Single dispatch point. Every tool call in the process goes through here."""
    spec = REGISTRY.get(name)
    if spec is None:
        raise KeyError(f"unknown tool {name!r}")
    if spec.tier is Tier.MUTATE and not kwargs.get("token"):
        raise PermissionError(f"{name} is a MUTATE tool and requires a reservation token")
    return spec.handler(session, **kwargs)


def manifest() -> list[dict[str, str]]:
    return [
        {"name": s.name, "tier": s.tier.value, "summary": s.summary}
        for s in sorted(REGISTRY.values(), key=lambda s: (s.tier.value, s.name))
    ]

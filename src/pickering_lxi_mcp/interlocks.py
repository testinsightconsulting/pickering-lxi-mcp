"""The interlocks, and why they are checked against connectivity rather than intent.

On a programmable supply the dangerous mistake is a number: 400 V where 4 V was
meant. On a switching matrix the dangerous mistake is a *graph*. Nobody ever
asks to short the supply to ground; they route the supply to a DUT pin, then
route that pin to ground for a continuity measurement, and the short is the
composition of two individually reasonable requests. Neither request looks wrong
at the moment it is made.

So the check here is not "is this route forbidden". It is: given every
crosspoint that is closed right now, plus every crosspoint this route would
close, plus the hard-wired patch leads, does any forbidden pair of endpoints end
up in the same connected component? That question is answered before a relay
moves, and a route that fails it is refused whole.

The other three rules are ordinary and still worth having: an armed-before-you-
switch gate, a per-subunit closure ceiling, and endpoints that may take part in
only one route at a time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .errors import InterlockError
from .topology import Node, Operation, Topology


@dataclass(frozen=True)
class InterlockPolicy:
    """Declared in the topology file, enforced in one place."""

    require_arm: bool = True
    max_closures_per_subunit: int | None = None
    forbidden_pairs: tuple[tuple[str, str], ...] = ()
    exclusive_endpoints: frozenset[str] = frozenset()
    enforce_power_limits: bool = True

    @classmethod
    def from_spec(cls, spec: dict[str, Any], topology: Topology) -> InterlockPolicy:
        pairs: list[tuple[str, str]] = []
        for pair in spec.get("forbidden_pairs", []):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise InterlockError("each entry in 'forbidden_pairs' must be a pair of endpoints")
            a, b = str(pair[0]), str(pair[1])
            topology.endpoint(a)
            topology.endpoint(b)
            pairs.append((a, b))

        exclusive = frozenset(str(n) for n in spec.get("exclusive_endpoints", []))
        for name in exclusive:
            topology.endpoint(name)

        limit = spec.get("max_closures_per_subunit")
        return cls(
            require_arm=bool(spec.get("require_arm", True)),
            max_closures_per_subunit=None if limit is None else int(limit),
            forbidden_pairs=tuple(pairs),
            exclusive_endpoints=exclusive,
            enforce_power_limits=bool(spec.get("enforce_power_limits", True)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "require_arm": self.require_arm,
            "max_closures_per_subunit": self.max_closures_per_subunit,
            "forbidden_pairs": [list(p) for p in self.forbidden_pairs],
            "exclusive_endpoints": sorted(self.exclusive_endpoints),
            "enforce_power_limits": self.enforce_power_limits,
        }


class _Components:
    """Union-find over switch-graph nodes. Small, and hot on every route."""

    def __init__(self) -> None:
        self._parent: dict[Node, Node] = {}

    def find(self, node: Node) -> Node:
        parent = self._parent.setdefault(node, node)
        while parent != node:
            node, parent = parent, self._parent.setdefault(parent, parent)
        return node

    def union(self, a: Node, b: Node) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def connected(self, a: Node, b: Node) -> bool:
        return self.find(a) == self.find(b)


def connectivity(
    topology: Topology, operations: Iterable[Operation]
) -> _Components:
    """Which lines are electrically common, given a set of closed crosspoints."""

    components = _Components()
    for a, b in topology.links:
        components.union(a, b)
    for op in operations:
        components.union(
            (op.card, op.subunit, "row", op.row),
            (op.card, op.subunit, "column", op.column),
        )
    return components


def overloads(
    topology: Topology, policy: InterlockPolicy, operations: Iterable[Operation]
) -> list[str]:
    """Source/destination pairs where a legitimate path carries too much power.

    Connectivity asks *whether* two things are common. This asks *what arrives*
    when they are. A DC fixture's dangerous state is a short; an RF fixture's is
    also an overload -- a +20 dBm generator reaching a +10 dBm receiver front
    end through a path nobody declared forbidden, because there is nothing wrong
    with the path. Same graph, different question.

    Deliberately not modelled: insertion loss, pad values and coupling. Treating
    the path as lossless is the conservative direction (it over-reports rather
    than under-reports), and any figure that depended on loss would be asserted
    from a datasheet rather than measured, which is a worse kind of number to
    hang a damage limit on. Frequency is not modelled at all -- isolation is a
    curve, not a boolean, and this graph has no notion of one.
    """

    if not policy.enforce_power_limits:
        return []

    sources = [e for e in topology.endpoints.values() if e.max_output_dbm is not None]
    sinks = [e for e in topology.endpoints.values() if e.max_input_dbm is not None]
    if not sources or not sinks:
        return []

    components = connectivity(topology, operations)
    problems: list[str] = []
    for source in sources:
        for sink in sinks:
            if source.name == sink.name:
                continue
            if source.max_output_dbm is None or sink.max_input_dbm is None:
                continue
            margin = source.max_output_dbm - sink.max_input_dbm
            if margin <= 0:
                continue
            if components.connected(source.node, sink.node):
                problems.append(
                    f"{source.name!r} can deliver up to {source.max_output_dbm:+.1f} dBm into "
                    f"{sink.name!r}, rated {sink.max_input_dbm:+.1f} dBm — {margin:.1f} dB over"
                )
    return sorted(problems)


def describe_violations(
    topology: Topology, policy: InterlockPolicy, operations: Iterable[Operation]
) -> list[str]:
    """Every rule a given set of closed crosspoints breaks, without raising.

    ``check_route`` answers "may I do this next", which is a question about a
    proposed change and stops at the first refusal. This answers "is the fixture
    I am looking at one this policy would ever have allowed", which is a
    question about a state someone else produced -- a chassis found already
    switched at startup, most of all. It reports everything rather than the
    first thing, because whoever has to decide what to do about it wants the
    whole list.
    """

    operations = tuple(operations)
    problems: list[str] = []

    counts: dict[tuple[str, int], int] = {}
    for op in operations:
        counts[(op.card, op.subunit)] = counts.get((op.card, op.subunit), 0) + 1
    for (card, subunit), count in sorted(counts.items()):
        ceiling = policy.max_closures_per_subunit
        try:
            hardware_ceiling = topology.subunit(card, subunit).closure_limit
        except Exception:
            problems.append(f"{card} subunit {subunit} is not described by this topology")
            continue
        limit = hardware_ceiling if ceiling is None else min(ceiling, hardware_ceiling)
        if count > limit:
            problems.append(
                f"{card} subunit {subunit} has {count} crosspoints closed, over the limit of {limit}"
            )

    components = connectivity(topology, operations)
    for a, b in policy.forbidden_pairs:
        if components.connected(topology.endpoint(a).node, topology.endpoint(b).node):
            problems.append(f"{a!r} and {b!r} are already electrically common")

    problems.extend(overloads(topology, policy, operations))
    return problems


def check_route(
    topology: Topology,
    policy: InterlockPolicy,
    *,
    closed: set[Operation],
    proposed: Iterable[Operation],
    endpoints: tuple[str, str],
    armed: bool,
    endpoints_in_use: dict[str, str],
) -> None:
    """Refuse a route before anything is switched, or return quietly.

    ``closed`` is what is closed now; ``proposed`` is what the route would add.
    Every rule is evaluated against the union, so a route is judged by the state
    it would produce rather than by the request that produced it.
    """

    proposed = tuple(proposed)
    source, target = endpoints

    if policy.require_arm and not armed:
        raise InterlockError(
            "the chassis interlock is not armed; call arm_interlock before routing. "
            "Arming is an explicit acknowledgement that the fixture is safe to energise."
        )

    for name in (source, target):
        if name in policy.exclusive_endpoints:
            holder = endpoints_in_use.get(name)
            if holder is not None:
                raise InterlockError(
                    f"endpoint {name!r} is exclusive and is already part of route {holder!r}; "
                    "unroute that first"
                )

    prospective = set(closed) | set(proposed)

    counts: dict[tuple[str, int], int] = {}
    for op in prospective:
        counts[(op.card, op.subunit)] = counts.get((op.card, op.subunit), 0) + 1
    for (card, subunit), count in counts.items():
        ceiling = policy.max_closures_per_subunit
        hardware_ceiling = topology.subunit(card, subunit).closure_limit
        limit = hardware_ceiling if ceiling is None else min(ceiling, hardware_ceiling)
        if count > limit:
            raise InterlockError(
                f"routing would leave {count} crosspoints closed on {card} subunit {subunit}, "
                f"over the limit of {limit}"
            )

    components = connectivity(topology, prospective)
    for a, b in policy.forbidden_pairs:
        node_a = topology.endpoint(a).node
        node_b = topology.endpoint(b).node
        if components.connected(node_a, node_b):
            raise InterlockError(
                f"refused: this route would make {a!r} and {b!r} electrically common, "
                f"which the topology forbids. Nothing was switched. "
                f"(Requested {source!r} to {target!r}.)"
            )

    already = set(overloads(topology, policy, closed))
    for problem in overloads(topology, policy, prospective):
        if problem in already:
            continue
        raise InterlockError(
            f"refused on power: {problem}. The path is not forbidden — the level on it is. "
            f"Nothing was switched. (Requested {source!r} to {target!r}.)"
        )


def check_crosspoint(
    topology: Topology,
    policy: InterlockPolicy,
    *,
    closed: set[Operation],
    operation: Operation,
    state: bool,
    armed: bool,
) -> None:
    """The same rules, for the low-level typed crosspoint tool.

    A tool that names a crosspoint directly is still a tool an agent can call,
    so it gets the same interlock treatment as a named route. The escape hatch
    that skips the checks is the one nobody should build.
    """

    if policy.require_arm and not armed:
        raise InterlockError(
            "the chassis interlock is not armed; call arm_interlock before switching"
        )
    if not state:
        return

    check_route(
        topology,
        policy,
        closed=closed,
        proposed=(operation,),
        endpoints=(str(operation), str(operation)),
        armed=armed,
        endpoints_in_use={},
    )

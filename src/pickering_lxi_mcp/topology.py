"""Logical endpoints, and the graph that turns two names into crosspoints.

This is the Switch Path Manager idea, kept small enough to read in one sitting.
A test engineer does not think in crosspoints; they think "connect the scope to
DUT pin A1". The topology file is the map from those names to physical lines on
physical subunits, plus the hard-wired patch leads between cards. Routing is
then a shortest-path search over that graph, and the answer is an ordered list
of switch operations.

Two properties matter more than the search itself:

* The plan is computed before anything is switched, so it can be shown to a
  human, checked against the interlocks, and refused as a whole. A router that
  closes crosspoints as it discovers them cannot be refused half way.
* Operations are content-addressed by ``(card, subunit, row, column)``, so two
  routes that share a crosspoint are seen to share it. That is what makes
  reference-counted teardown correct instead of approximately correct.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .driver import ROUTABLE_SUBUNITS, SUBUNIT_MATRIX, CardInfo, SubunitInfo
from .errors import PathError, TopologyError

# A node in the switch graph: one physical line on one subunit.
#   (card alias, subunit, "row" | "column", index)
Node = tuple[str, int, str, int]

ROW = "row"
COLUMN = "column"
_LINES = (ROW, COLUMN)


@dataclass(frozen=True)
class Endpoint:
    """A name a human uses, bound to one physical line."""

    name: str
    node: Node
    role: str = "signal"
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        alias, subunit, line, index = self.node
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "card": alias,
            "subunit": subunit,
            "line": line,
            "index": index,
        }


@dataclass(frozen=True)
class Operation:
    """One crosspoint to operate. Hashable, so routes can share them."""

    card: str
    subunit: int
    row: int
    column: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "card": self.card,
            "subunit": self.subunit,
            "row": self.row,
            "column": self.column,
        }

    def __str__(self) -> str:
        return f"{self.card}/sub{self.subunit}({self.row},{self.column})"


@dataclass(frozen=True)
class SwitchPath:
    """A computed, not-yet-applied route between two endpoints."""

    source: str
    target: str
    operations: tuple[Operation, ...]
    nodes: tuple[Node, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.source,
            "to": self.target,
            "hops": len(self.operations),
            "operations": [op.as_dict() for op in self.operations],
            "nodes": [list(n) for n in self.nodes],
        }


class Topology:
    """The loaded map: cards, endpoints, hard-wired links, interlock policy."""

    def __init__(self, spec: dict[str, Any], source: str = "<inline>") -> None:
        self.source = source
        self.name: str = str(spec.get("name", "unnamed"))
        self.description: str = str(spec.get("description", ""))
        self.cards: tuple[CardInfo, ...] = _parse_cards(spec)
        self._card_by_alias = {c.alias: c for c in self.cards}
        self.endpoints: dict[str, Endpoint] = _parse_endpoints(spec, self._card_by_alias)
        self.links: tuple[tuple[Node, Node], ...] = _parse_links(spec, self._card_by_alias)
        self.interlocks: dict[str, Any] = dict(spec.get("interlocks", {}))
        self._adjacency = self._build_adjacency()

    # -- loading ----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> Topology:
        p = Path(path)
        if not p.is_file():
            raise TopologyError(f"no topology file at {p}")
        try:
            spec = json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            raise TopologyError(f"{p} is not valid JSON: {exc}") from exc
        return cls(spec, source=str(p))

    @classmethod
    def bundled(cls, name: str = "dut_bench") -> Topology:
        """Load one of the example topologies shipped inside the package."""
        return cls.load(Path(__file__).resolve().parent / "topologies" / f"{name}.json")

    @classmethod
    def bundled_names(cls) -> list[str]:
        root = Path(__file__).resolve().parent / "topologies"
        return sorted(p.stem for p in root.glob("*.json"))

    # -- introspection ----------------------------------------------------
    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "cards": [c.as_dict() for c in self.cards],
            "endpoints": [e.as_dict() for e in self.endpoints.values()],
            "links": [[list(a), list(b)] for a, b in self.links],
            "interlocks": self.interlocks,
        }

    def endpoint(self, name: str) -> Endpoint:
        ep = self.endpoints.get(name)
        if ep is None:
            raise TopologyError(
                f"unknown endpoint {name!r}; this topology defines {sorted(self.endpoints)}"
            )
        return ep

    def card(self, alias: str) -> CardInfo:
        card = self._card_by_alias.get(alias)
        if card is None:
            raise TopologyError(f"unknown card {alias!r}; have {sorted(self._card_by_alias)}")
        return card

    def subunit(self, alias: str, subunit: int) -> SubunitInfo:
        return self.card(alias).subunit(subunit)

    def endpoints_on(self, node: Node) -> list[str]:
        return sorted(name for name, ep in self.endpoints.items() if ep.node == node)

    # -- the graph --------------------------------------------------------
    def _build_adjacency(self) -> dict[Node, list[tuple[Node, Operation | None]]]:
        """Every edge an agent could route over.

        A matrix subunit contributes one switchable edge per crosspoint. A mux
        subunit is a matrix with one row, which is exactly how the driver
        reports it, so it needs no special case here. Declared links are
        zero-cost edges with no operation -- a patch lead is not something the
        server can switch, only something it must know about.
        """

        adjacency: dict[Node, list[tuple[Node, Operation | None]]] = {}

        def connect(a: Node, b: Node, op: Operation | None) -> None:
            adjacency.setdefault(a, []).append((b, op))
            adjacency.setdefault(b, []).append((a, op))

        for card in self.cards:
            for sub in card.subunits:
                if sub.type not in ROUTABLE_SUBUNITS:
                    continue
                for row in range(1, sub.rows + 1):
                    for column in range(1, sub.columns + 1):
                        connect(
                            (card.alias, sub.subunit, ROW, row),
                            (card.alias, sub.subunit, COLUMN, column),
                            Operation(card.alias, sub.subunit, row, column),
                        )

        for a, b in self.links:
            connect(a, b, None)

        return adjacency

    def find_path(self, source: str, target: str) -> SwitchPath:
        """Fewest switch closures between two named endpoints.

        Breadth-first, so the returned plan is the one that energises the fewest
        relays. Relay closures are the wear item on a switching card and the
        thing a closure limit counts, so "fewest hops" is the right objective
        even before it is the simplest one.
        """

        src = self.endpoint(source)
        dst = self.endpoint(target)
        if src.node == dst.node:
            raise PathError(
                f"{source!r} and {target!r} are the same physical line "
                f"({_node_str(src.node)}); they are already common"
            )

        previous: dict[Node, tuple[Node, Operation | None]] = {}
        seen = {src.node}
        queue: deque[Node] = deque([src.node])

        while queue:
            node = queue.popleft()
            if node == dst.node:
                return self._reconstruct(source, target, src.node, dst.node, previous)
            for neighbour, op in self._adjacency.get(node, ()):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                previous[neighbour] = (node, op)
                queue.append(neighbour)

        raise PathError(
            f"no switch path from {source!r} ({_node_str(src.node)}) to "
            f"{target!r} ({_node_str(dst.node)}) in topology {self.name!r}; "
            "they are on subunits with no crosspoint or link between them"
        )

    def _reconstruct(
        self,
        source: str,
        target: str,
        start: Node,
        end: Node,
        previous: dict[Node, tuple[Node, Operation | None]],
    ) -> SwitchPath:
        operations: list[Operation] = []
        nodes: list[Node] = [end]
        cursor = end
        while cursor != start:
            cursor, op = previous[cursor]
            nodes.append(cursor)
            if op is not None:
                operations.append(op)
        nodes.reverse()
        operations.reverse()
        return SwitchPath(
            source=source, target=target, operations=tuple(operations), nodes=tuple(nodes)
        )


# ---------------------------------------------------------------------------
# Parsing. Everything below exists to make a bad topology fail loudly at load
# time, in the process that can still say something useful about it.
# ---------------------------------------------------------------------------


def _parse_cards(spec: dict[str, Any]) -> tuple[CardInfo, ...]:
    raw = spec.get("cards")
    if not isinstance(raw, dict) or not raw:
        raise TopologyError("topology needs a non-empty 'cards' object")

    cards: list[CardInfo] = []
    for alias, body in raw.items():
        if not isinstance(body, dict):
            raise TopologyError(f"card {alias!r} must be an object")
        subunits_raw = body.get("subunits")
        if not isinstance(subunits_raw, list) or not subunits_raw:
            raise TopologyError(f"card {alias!r} needs a non-empty 'subunits' list")

        subunits: list[SubunitInfo] = []
        for index, sub in enumerate(subunits_raw, start=1):
            if not isinstance(sub, dict):
                raise TopologyError(f"card {alias!r} subunit {index} must be an object")
            sub_type = str(sub.get("type", SUBUNIT_MATRIX)).upper()
            rows = int(sub.get("rows", 1))
            columns = int(sub.get("columns", 0))
            if rows < 1 or columns < 1:
                raise TopologyError(
                    f"card {alias!r} subunit {index}: rows and columns must both be >= 1"
                )
            subunits.append(
                SubunitInfo(
                    subunit=int(sub.get("subunit", index)),
                    type=sub_type,
                    rows=rows,
                    columns=columns,
                    closure_limit=int(sub.get("closure_limit", rows * columns)),
                    settle_time_us=int(sub.get("settle_time_us", 3000)),
                )
            )

        cards.append(
            CardInfo(
                alias=str(alias),
                bus=int(body.get("bus", 0)),
                device=int(body.get("device", 0)),
                card_id=str(body.get("card_id", "unknown")),
                subunits=tuple(subunits),
            )
        )
    return tuple(cards)


def _parse_node(raw: Any, cards: dict[str, CardInfo], context: str) -> Node:
    if not isinstance(raw, dict):
        raise TopologyError(f"{context} must be an object with card/subunit/line/index")

    alias = str(raw.get("card", ""))
    card = cards.get(alias)
    if card is None:
        raise TopologyError(f"{context}: unknown card {alias!r}; have {sorted(cards)}")

    subunit_number = int(raw.get("subunit", 1))
    sub = card.subunit(subunit_number)

    line = str(raw.get("line", "")).lower()
    if line not in _LINES:
        raise TopologyError(f"{context}: 'line' must be one of {list(_LINES)}, got {line!r}")

    index = int(raw.get("index", 0))
    limit = sub.rows if line == ROW else sub.columns
    if not (1 <= index <= limit):
        raise TopologyError(
            f"{context}: {line} {index} is outside 1..{limit} on {alias} subunit {subunit_number}"
        )

    return (alias, subunit_number, line, index)


def _parse_endpoints(spec: dict[str, Any], cards: dict[str, CardInfo]) -> dict[str, Endpoint]:
    raw = spec.get("endpoints")
    if not isinstance(raw, dict) or not raw:
        raise TopologyError("topology needs a non-empty 'endpoints' object")

    endpoints: dict[str, Endpoint] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise TopologyError(f"endpoint {name!r} must be an object")
        node = _parse_node(body, cards, f"endpoint {name!r}")
        endpoints[str(name)] = Endpoint(
            name=str(name),
            node=node,
            role=str(body.get("role", "signal")),
            description=str(body.get("description", "")),
        )
    return endpoints


def _parse_links(spec: dict[str, Any], cards: dict[str, CardInfo]) -> tuple[tuple[Node, Node], ...]:
    raw = spec.get("links", [])
    if not isinstance(raw, list):
        raise TopologyError("'links' must be a list of two-element [from, to] pairs")

    links: list[tuple[Node, Node]] = []
    for index, pair in enumerate(raw, start=1):
        if not isinstance(pair, list) or len(pair) != 2:
            raise TopologyError(f"link {index} must be a two-element [from, to] pair")
        a = _parse_node(pair[0], cards, f"link {index} 'from'")
        b = _parse_node(pair[1], cards, f"link {index} 'to'")
        if a == b:
            raise TopologyError(f"link {index} connects a line to itself")
        links.append((a, b))
    return tuple(links)


def _node_str(node: Node) -> str:
    alias, subunit, line, index = node
    return f"{alias}/sub{subunit} {line} {index}"

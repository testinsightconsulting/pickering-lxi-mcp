"""Chassis session: reservations, the mutation gate, and reference-counted routes.

The lifecycle is the same for every chassis:

    connect -> discover -> reserve -> arm -> route -> observe -> unroute -> release

Observation is never gated. Reading which crosspoints are closed is the single
most common thing an agent needs to do in a shared lab, and if that required
taking the chassis, agents would learn to take chassis they do not need. Cheap
observation is what makes strict mutation acceptable.

Routes are reference counted per crosspoint. Two routes through the same matrix
will legitimately share a crosspoint; tearing down one of them must not open a
crosspoint the other is still relying on. Counting is the difference between a
teardown that is correct and one that is usually correct.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from . import interlocks
from .driver import Backend
from .errors import DriverError, InterlockError, ReconciliationError, ReservationError
from .interlocks import InterlockPolicy
from .topology import Operation, SwitchPath, Topology


def guarded(method: Any) -> Any:
    """Run this method while holding the session lock.

    Applied to everything that touches the route table, the reservation or the
    armed flag -- and, for mutations, across the switching too, so that
    check-and-apply is one indivisible step.
    """

    @wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


@dataclass
class Reservation:
    token: str
    owner: str
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at


@dataclass
class Route:
    """One open logical connection, and the crosspoints holding it up."""

    route_id: str
    source: str
    target: str
    operations: tuple[Operation, ...]
    owner: str
    opened_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "from": self.source,
            "to": self.target,
            "owner": self.owner,
            "operations": [op.as_dict() for op in self.operations],
        }


def route_id(source: str, target: str) -> str:
    """Routes are undirected: a-to-b and b-to-a are the same connection."""
    a, b = sorted((source, target))
    return f"{a}<->{b}"


@dataclass
class ChassisSession:
    """One chassis, one topology, one optional reservation, one journal."""

    backend: Backend
    topology: Topology
    policy: InterlockPolicy
    reservation: Reservation | None = None
    armed: bool = False
    routes: dict[str, Route] = field(default_factory=dict)
    journal: list[str] = field(default_factory=list)

    # Crosspoints found closed that no route in this process owns. A chassis is
    # not a blank sheet at startup: a previous process may have died holding a
    # fixture live, or another program may be using the rack. Until somebody
    # says what these are, this server refuses to switch -- see reconcile().
    # "Unowned" is the word throughout: on the wire, in the code, in the
    # refusal text. A crosspoint is owned when some route in THIS process holds
    # it, and unowned otherwise -- which says nothing about whether it is
    # legitimate, only that nothing here can say what depends on it.
    unowned: set[Operation] = field(default_factory=set)
    reconciled: bool = False

    # One agent is routinely several threads: the MCP SDK runs synchronous tool
    # bodies in a worker pool, so two tool calls on one connection -- let alone
    # two connections under one lease -- genuinely execute in parallel.
    #
    # That breaks the interlock unless the check and the switching are one
    # atomic step. "Is this route safe given what is closed" and "close it" must
    # not be separated, because between them another thread can close the
    # crosspoint that makes the answer wrong. Both routes pass their own check,
    # both apply, and the composition is the short neither of them asked for.
    #
    # So every mutation holds this lock across check-and-apply. Serialising is
    # free: a relay takes milliseconds to settle, which dwarfs anything the lock
    # costs, and one process owns one fabric, so a process-local lock is the
    # whole answer -- no distributed coordination at the device level.
    #
    # Observation deliberately does NOT hold it while touching hardware. Reads
    # are the thing agents do constantly, and a read that blocks switching would
    # be a worse bug than a read that is a few milliseconds stale.
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @classmethod
    def build(cls, backend: Backend, topology: Topology) -> ChassisSession:
        session = cls(
            backend=backend,
            topology=topology,
            policy=InterlockPolicy.from_spec(topology.interlocks, topology),
        )
        session.reconcile()
        return session

    # -- startup reconciliation -------------------------------------------
    @guarded
    def reconcile(self) -> dict[str, Any]:
        """Read what is actually closed before believing anything.

        The failure this exists for: the process restarts, the route table comes
        back empty, and the relays do not. The server then believes nothing is
        closed while the fixture is live -- and the interlock, which reasons
        from that table, will happily authorise the very short it exists to
        prevent. An empty in-memory model of a chassis that is not empty is
        worse than no model at all, because it is confidently wrong.

        So: read every subunit, record anything closed that no route here owns,
        and if there is any, refuse to switch until a person decides between
        adopting the state and clearing it. Observation stays open throughout,
        because deciding requires looking first.
        """

        owned = {op for route in self.routes.values() for op in route.operations}
        found: set[Operation] = set()

        for card in self.backend.cards():
            for sub in card.subunits:
                grid = self.backend.view_subunit(card.alias, sub.subunit)
                for r, line in enumerate(grid, start=1):
                    for c, closed in enumerate(line, start=1):
                        if closed:
                            found.add(Operation(card.alias, sub.subunit, r, c))

        self.unowned = found - owned
        self.reconciled = not self.unowned
        self._log(f"reconcile found={len(found)} unowned={len(self.unowned)}")
        return self.reconciliation_status()

    def reconciliation_status(self) -> dict[str, Any]:
        """What was found at startup, and what it breaks. Never gated."""
        problems = interlocks.describe_violations(
            self.topology, self.policy, self._closed_operations()
        )
        return {
            "reconciled": self.reconciled,
            "unowned_crosspoints": sorted(
                (op.as_dict() for op in self.unowned),
                key=lambda d: (d["card"], d["subunit"], d["row"], d["column"]),
            ),
            "violations": problems,
            "resolve_with": (
                []
                if self.reconciled
                else ["adopt_existing_state", "clear_existing_state"]
            ),
        }

    # -- observe: never gated ---------------------------------------------
    def describe(self) -> dict[str, Any]:
        # backend I/O first, outside the lock; the counters below are a snapshot
        info = dict(self.backend.describe())
        info.update(
            {
                "topology": self.topology.name,
                "topology_source": self.topology.source,
                "endpoint_count": len(self.topology.endpoints),
                "interlock_armed": self.armed,
                "reconciled": self.reconciled,
                "reserved_by": self.reservation.owner if self._live_reservation() else None,
                "open_routes": len(self.routes),
            }
        )
        return info

    def list_cards(self) -> list[dict[str, Any]]:
        return [card.as_dict() for card in self.backend.cards()]

    def list_endpoints(self) -> list[dict[str, Any]]:
        return [ep.as_dict() for ep in self.topology.endpoints.values()]

    @guarded
    def list_routes(self) -> list[dict[str, Any]]:
        return [r.as_dict() for r in self.routes.values()]

    @guarded
    def plan(self, source: str, target: str) -> dict[str, Any]:
        """Compute a route and dry-run the interlocks against it.

        Nothing is switched. This is the tool an agent should reach for first:
        it turns "would this be allowed" into a question that can be asked
        without taking the chassis.
        """

        path = self.topology.find_path(source, target)
        result: dict[str, Any] = path.as_dict()
        result["already_open"] = route_id(source, target) in self.routes

        try:
            self._check(path)
        except InterlockError as exc:
            result["permitted"] = False
            result["refusal"] = str(exc)
            return result

        result["permitted"] = True
        result["refusal"] = None
        return result

    @guarded
    def crosspoint(self, card: str, subunit: int, row: int, column: int) -> dict[str, Any]:
        closed = self.backend.view_crosspoint(card, subunit, row, column)
        return {
            "card": card,
            "subunit": subunit,
            "row": row,
            "column": column,
            "closed": closed,
            "held_by_routes": sorted(
                r.route_id
                for r in self.routes.values()
                if Operation(card, subunit, row, column) in r.operations
            ),
        }

    def subunit_state(self, card: str, subunit: int) -> dict[str, Any]:
        info = self.topology.subunit(card, subunit)
        state = self.backend.view_subunit(card, subunit)
        closed = [
            {"row": r + 1, "column": c + 1}
            for r, line in enumerate(state)
            for c, bit in enumerate(line)
            if bit
        ]
        return {
            "card": card,
            "subunit": subunit,
            "type": info.type,
            "rows": info.rows,
            "columns": info.columns,
            "closure_limit": info.closure_limit,
            "settle_time_us": info.settle_time_us,
            "closed_count": len(closed),
            "closed": closed,
        }

    @guarded
    def interlock_status(self) -> dict[str, Any]:
        return {
            "armed": self.armed,
            "policy": self.policy.as_dict(),
            "reconciliation": self.reconciliation_status(),
            "closed_crosspoints": len(self._closed_operations()),
            "open_routes": sorted(self.routes),
        }

    def verify_topology(self) -> dict[str, Any]:
        """Compare what the topology claims against what the chassis reports.

        On the simulator this is trivially true, which is the point: the same
        call against real hardware is what catches a topology written for last
        quarter's rack.
        """

        actual = {card.alias: card for card in self.backend.cards()}
        problems: list[str] = []

        for declared in self.topology.cards:
            found = actual.get(declared.alias)
            if found is None:
                problems.append(f"card {declared.alias!r} is in the topology but not in the chassis")
                continue
            for sub in declared.subunits:
                try:
                    live = found.subunit(sub.subunit)
                except DriverError as exc:
                    problems.append(str(exc))
                    continue
                if (live.rows, live.columns) != (sub.rows, sub.columns):
                    problems.append(
                        f"{declared.alias} subunit {sub.subunit}: topology says "
                        f"{sub.rows}x{sub.columns}, chassis reports {live.rows}x{live.columns}"
                    )

        for alias in sorted(set(actual) - {c.alias for c in self.topology.cards}):
            problems.append(f"card {alias!r} is in the chassis but not in the topology")

        return {"ok": not problems, "problems": problems}

    # -- reservations ------------------------------------------------------
    @guarded
    def reserve(self, owner: str, ttl_seconds: float = 900.0) -> Reservation:
        if self._live_reservation() and self.reservation is not None:
            if self.reservation.owner != owner:
                raise ReservationError(
                    f"chassis is reserved by {self.reservation.owner!r} until that reservation "
                    "expires or is released"
                )
            return self.reservation
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.reservation = Reservation(
            token=uuid.uuid4().hex, owner=owner, expires_at=time.monotonic() + ttl_seconds
        )
        self._log(f"reserve owner={owner} ttl={ttl_seconds}")
        return self.reservation

    @guarded
    def release(self, token: str) -> dict[str, Any]:
        """Releasing tears the fixture down. A dropped agent must not leave it live."""
        self._require(token)
        opened = sorted(self.routes)
        self.clear_all_routes(token)
        self.armed = False
        self.reservation = None
        self._log("release")
        return {"status": "released", "routes_cleared": opened, "interlock_armed": False}

    # -- the gate ----------------------------------------------------------
    def _require(self, token: str) -> Reservation:
        res = self.reservation
        if res is None:
            raise ReservationError("no reservation is held; call reserve_chassis first")
        if res.expired:
            self.reservation = None
            self.armed = False
            raise ReservationError("reservation has expired; reserve again")
        if token != res.token:
            raise ReservationError("reservation token does not match the active reservation")
        return res

    def _require_reconciled(self) -> None:
        """Refuse to energise a fixture whose current state nobody has claimed."""
        if self.reconciled:
            return
        listing = ", ".join(str(op) for op in sorted(self.unowned, key=str)[:6])
        more = "" if len(self.unowned) <= 6 else f" (+{len(self.unowned) - 6} more)"
        raise ReconciliationError(
            f"{len(self.unowned)} crosspoint(s) were already closed on this chassis when "
            f"this server started, and no route here owns them: {listing}{more}. "
            "The fixture may be live. Call adopt_existing_state to keep that state and "
            "count it in every future interlock check, or clear_existing_state to open "
            "everything and start from a known-safe chassis. Observation works meanwhile."
        )

    def _live_reservation(self) -> bool:
        return self.reservation is not None and not self.reservation.expired

    # -- mutate: always gated ----------------------------------------------
    @guarded
    def adopt_existing_state(self, token: str, confirm: str) -> dict[str, Any]:
        """Keep what was found, and hold every future check to it.

        Adoption does not switch anything. It moves the found crosspoints into
        the set the interlock reasons over, so a route that would compose a
        short with them is refused exactly as if this process had closed them.
        They belong to no route, so no unroute will open them; clearing is what
        removes them.

        Refused if the found state is one this policy would never have
        permitted. Adopting a fixture that is already shorted would make the
        violation the baseline every later check is measured against, which is
        the one outcome worse than refusing to serve.
        """

        self._require(token)
        if self.reconciled:
            return {"status": "nothing_to_adopt", **self.reconciliation_status()}

        expected = "adopt the state on the chassis"
        if confirm.strip().lower() != expected:
            raise ReconciliationError(
                f"adopt_existing_state requires confirm={expected!r} exactly; nothing changed"
            )

        problems = interlocks.describe_violations(self.topology, self.policy, self.unowned)
        if problems:
            raise ReconciliationError(
                "the state on this chassis breaks the topology's own rules, so it cannot be "
                f"adopted as a baseline: {'; '.join(problems)}. Use clear_existing_state, or "
                "fix the topology if these connections are legitimate."
            )

        self.reconciled = True
        self._log(f"adopt unowned={len(self.unowned)}")
        return {"status": "adopted", **self.reconciliation_status()}

    @guarded
    def clear_existing_state(self, token: str, confirm: str) -> dict[str, Any]:
        """Open every crosspoint and start from a chassis whose state is known."""

        self._require(token)
        expected = "open every crosspoint on the chassis"
        if confirm.strip().lower() != expected:
            raise ReconciliationError(
                f"clear_existing_state requires confirm={expected!r} exactly; nothing changed"
            )

        opened = len(self.unowned)
        self.backend.clear_all()
        self.routes.clear()
        self.unowned.clear()
        self.reconciled = True
        self._log(f"clear_existing_state opened={opened}")
        return {"status": "cleared", "crosspoints_opened": opened, **self.reconciliation_status()}

    @guarded
    def arm(self, token: str, confirm: str) -> dict[str, Any]:
        """Arming is deliberately awkward.

        It takes a literal acknowledgement rather than a boolean, because a
        boolean argument is something a model fills in from context and a fixed
        string is something it has to mean.
        """

        self._require(token)
        self._require_reconciled()
        expected = "the fixture is safe to energise"
        if confirm.strip().lower() != expected:
            raise InterlockError(
                f"arm_interlock requires confirm={expected!r} exactly; the interlock is still open"
            )
        self.armed = True
        self._log("arm")
        return {"armed": True}

    @guarded
    def disarm(self, token: str) -> dict[str, Any]:
        self._require(token)
        self.armed = False
        self._log("disarm")
        return {"armed": False}

    @guarded
    def route(self, token: str, source: str, target: str) -> dict[str, Any]:
        res = self._require(token)
        self._require_reconciled()
        rid = route_id(source, target)
        if rid in self.routes:
            return {"route_id": rid, "status": "already_open", **self.routes[rid].as_dict()}

        path = self.topology.find_path(source, target)
        self._check(path)

        applied: list[Operation] = []
        try:
            for op in path.operations:
                if not self._is_held(op):
                    self.backend.close_crosspoint(op.card, op.subunit, op.row, op.column)
                applied.append(op)
        except DriverError:
            self._rollback(applied)
            raise

        route = Route(
            route_id=rid,
            source=source,
            target=target,
            operations=path.operations,
            owner=res.owner,
            opened_at=time.time(),
        )
        self.routes[rid] = route
        self._log(f"route {rid} via {[str(op) for op in path.operations]}")
        return {"route_id": rid, "status": "open", **route.as_dict()}

    @guarded
    def unroute(self, token: str, source: str, target: str) -> dict[str, Any]:
        self._require(token)
        rid = route_id(source, target)
        route = self.routes.pop(rid, None)
        if route is None:
            return {"route_id": rid, "status": "not_open", "opened": []}

        opened: list[dict[str, Any]] = []
        retained: list[dict[str, Any]] = []
        for op in route.operations:
            if self._is_held(op):
                retained.append(op.as_dict())
                continue
            self.backend.open_crosspoint(op.card, op.subunit, op.row, op.column)
            opened.append(op.as_dict())

        self._log(f"unroute {rid} opened={len(opened)} retained={len(retained)}")
        return {
            "route_id": rid,
            "status": "closed",
            "opened": opened,
            "retained_for_other_routes": retained,
        }

    @guarded
    def clear_all_routes(self, token: str) -> dict[str, Any]:
        self._require(token)
        cleared = sorted(self.routes)
        adopted = len(self.unowned)
        self.routes.clear()
        self.unowned.clear()
        self.backend.clear_all()
        self.reconciled = True
        self._log(f"clear_all_routes {cleared} unowned={adopted}")
        return {
            "status": "cleared",
            "routes": cleared,
            "unowned_crosspoints_opened": adopted,
        }

    @guarded
    def set_crosspoint(
        self, token: str, card: str, subunit: int, row: int, column: int, state: bool
    ) -> dict[str, Any]:
        """Typed, bounds-checked, interlock-checked direct control.

        Present because commissioning a fixture genuinely needs it. Note what it
        is not: a passthrough. It cannot name a subunit that is not in the
        topology, cannot exceed the reported matrix size, and cannot close a
        crosspoint the interlocks refuse.
        """

        self._require(token)
        self._require_reconciled()
        info = self.topology.subunit(card, subunit)
        if not (1 <= row <= info.rows):
            raise ValueError(f"row {row} outside 1..{info.rows} on {card} subunit {subunit}")
        if not (1 <= column <= info.columns):
            raise ValueError(
                f"column {column} outside 1..{info.columns} on {card} subunit {subunit}"
            )

        op = Operation(card, subunit, row, column)
        if not state and op in self.unowned:
            raise InterlockError(
                f"crosspoint {op} was already closed when this server started and was adopted, "
                "so this process does not know what depends on it; use clear_all_routes to open "
                "everything deliberately"
            )
        if not state and self._is_held(op):
            holders = sorted(
                r.route_id for r in self.routes.values() if op in r.operations
            )
            raise InterlockError(
                f"crosspoint {op} is holding up route(s) {holders}; unroute instead of "
                "opening it directly"
            )

        interlocks.check_crosspoint(
            self.topology,
            self.policy,
            closed=self._closed_operations(),
            operation=op,
            state=state,
            armed=self.armed,
        )

        if state:
            self.backend.close_crosspoint(card, subunit, row, column)
        else:
            self.backend.open_crosspoint(card, subunit, row, column)
        self._log(f"set_crosspoint {op} -> {state}")
        return {"operation": op.as_dict(), "closed": state}

    # -- helpers -----------------------------------------------------------
    def _check(self, path: SwitchPath) -> None:
        interlocks.check_route(
            self.topology,
            self.policy,
            closed=self._closed_operations(),
            proposed=path.operations,
            endpoints=(path.source, path.target),
            armed=self.armed,
            endpoints_in_use=self._endpoints_in_use(),
        )

    def _closed_operations(self) -> set[Operation]:
        """Crosspoints closed by this server, from its own route table.

        Read from the route table rather than the chassis on purpose: the
        interlock must reason about the state this server is responsible for,
        and a shared chassis can have another session's closures in it that this
        one has no business tearing down.
        """

        return {op for route in self.routes.values() for op in route.operations} | self.unowned

    def _endpoints_in_use(self) -> dict[str, str]:
        in_use: dict[str, str] = {}
        for route in self.routes.values():
            in_use.setdefault(route.source, route.route_id)
            in_use.setdefault(route.target, route.route_id)
        return in_use

    def _is_held(self, op: Operation) -> bool:
        return any(op in route.operations for route in self.routes.values())

    def _rollback(self, applied: list[Operation]) -> None:
        for op in reversed(applied):
            if self._is_held(op):
                continue
            try:
                self.backend.open_crosspoint(op.card, op.subunit, op.row, op.column)
            except DriverError:  # pragma: no cover - best effort teardown
                self._log(f"rollback failed for {op}")

    def _log(self, entry: str) -> None:
        self.journal.append(entry)

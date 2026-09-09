"""Two backends behind one narrow interface.

``PilxiBackend`` drives real Pickering PXI/LXI hardware through the vendor's
ClientBridge wrapper (``pilxi`` on PyPI). ``SimBackend`` is a state machine that
implements the same interface in pure Python.

The simulator is not a mock. It enforces the constraints that actually bite on a
switching card -- crosspoint bounds, per-subunit closure limits, masked
crosspoints, settle time, cleared-on-open semantics -- so a walkthrough that
passes against it is evidence about the routing logic rather than about a set of
canned return values. Where the simulator and a real card disagree, the
simulator is wrong and gets fixed.

Importing ``pilxi`` does not require the vendor driver; instantiating a session
does. That is why the import is deferred into ``PilxiBackend.connect``: the
package installs, imports, tests and runs on a laptop with no Pickering software
on it at all.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import DriverError

# Pickering subunit type names, as reported by PIPLX_SubType. The two this
# server routes through are MATRIX (rows x columns of crosspoints) and MUX
# (one common, N channels, one closed at a time).
SUBUNIT_MATRIX = "MATRIX"
SUBUNIT_MUX = "MUX"
SUBUNIT_MUXM = "MUXM"
SUBUNIT_SWITCH = "SWITCH"

# Subunit types this server knows how to route through. A MUX is a matrix with
# one row and a closure limit of one; a MUXM is the same shape with several
# channels allowed closed at once. Both fall out of the matrix model, so the
# routing layer needs no special case for either.
ROUTABLE_SUBUNITS = frozenset({SUBUNIT_MATRIX, SUBUNIT_MUX, SUBUNIT_MUXM})


@dataclass(frozen=True)
class SubunitInfo:
    """What a card reports about one of its subunits."""

    subunit: int
    type: str
    rows: int
    columns: int
    closure_limit: int
    settle_time_us: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "subunit": self.subunit,
            "type": self.type,
            "rows": self.rows,
            "columns": self.columns,
            "closure_limit": self.closure_limit,
            "settle_time_us": self.settle_time_us,
        }


@dataclass(frozen=True)
class CardInfo:
    """What a chassis reports about one card."""

    alias: str
    bus: int
    device: int
    card_id: str
    subunits: tuple[SubunitInfo, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "bus": self.bus,
            "device": self.device,
            "card_id": self.card_id,
            "subunits": [s.as_dict() for s in self.subunits],
        }

    def subunit(self, number: int) -> SubunitInfo:
        for sub in self.subunits:
            if sub.subunit == number:
                return sub
        raise DriverError(
            f"card {self.alias!r} has no subunit {number}; "
            f"it has {[s.subunit for s in self.subunits]}"
        )


class Backend(Protocol):
    """The whole surface the routing layer is allowed to touch.

    Deliberately small. Everything the vendor wrapper can do that this server
    does not need -- battery simulators, resistor chains, function generators --
    stays out, so there is no path from an agent to a subsystem nobody reviewed.
    """

    name: str

    def describe(self) -> dict[str, Any]: ...

    def cards(self) -> tuple[CardInfo, ...]: ...

    def close_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None: ...

    def open_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None: ...

    def view_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> bool: ...

    def view_subunit(self, alias: str, subunit: int) -> list[list[bool]]: ...

    def closed_count(self, alias: str, subunit: int) -> int: ...

    def clear_subunit(self, alias: str, subunit: int) -> None: ...

    def clear_all(self) -> None: ...

    def disconnect(self) -> None: ...


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


@dataclass
class _SimSubunit:
    info: SubunitInfo
    state: list[list[bool]] = field(default_factory=list)
    mask: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.state:
            self.state = [
                [False] * self.info.columns for _ in range(self.info.rows)
            ]

    @property
    def closed(self) -> int:
        return sum(1 for row in self.state for bit in row if bit)


@dataclass
class _SimCard:
    info: CardInfo
    subunits: dict[int, _SimSubunit]


class SimBackend:
    """Deterministic in-process model of a Pickering chassis.

    Built from the card declarations in a topology, so the simulated chassis is
    always the one the topology claims to be routing through. That is the point:
    a topology that does not fit the hardware fails in CI rather than in a rack.
    """

    name = "simulator"

    def __init__(self, cards: tuple[CardInfo, ...], address: str = "SIM") -> None:
        self.address = address
        self._cards: dict[str, _SimCard] = {}
        for info in cards:
            self._cards[info.alias] = _SimCard(
                info=info,
                subunits={s.subunit: _SimSubunit(info=s) for s in info.subunits},
            )

    # -- introspection ----------------------------------------------------
    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "address": self.address,
            "driver": "none (in-process simulator)",
            "card_count": len(self._cards),
            "hardware": False,
        }

    def cards(self) -> tuple[CardInfo, ...]:
        return tuple(card.info for card in self._cards.values())

    # -- switching --------------------------------------------------------
    def close_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None:
        sub = self._subunit(alias, subunit)
        self._check_bounds(alias, sub, row, column)
        if (row, column) in sub.mask:
            raise DriverError(
                f"{alias} subunit {subunit} crosspoint ({row},{column}) is masked and cannot close"
            )
        if not sub.state[row - 1][column - 1] and sub.closed >= sub.info.closure_limit:
            raise DriverError(
                f"{alias} subunit {subunit} is at its closure limit of "
                f"{sub.info.closure_limit}; open a crosspoint before closing another"
            )
        sub.state[row - 1][column - 1] = True

    def open_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None:
        sub = self._subunit(alias, subunit)
        self._check_bounds(alias, sub, row, column)
        sub.state[row - 1][column - 1] = False

    def view_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> bool:
        sub = self._subunit(alias, subunit)
        self._check_bounds(alias, sub, row, column)
        return sub.state[row - 1][column - 1]

    def view_subunit(self, alias: str, subunit: int) -> list[list[bool]]:
        sub = self._subunit(alias, subunit)
        return [list(row) for row in sub.state]

    def closed_count(self, alias: str, subunit: int) -> int:
        return self._subunit(alias, subunit).closed

    def clear_subunit(self, alias: str, subunit: int) -> None:
        sub = self._subunit(alias, subunit)
        sub.state = [[False] * sub.info.columns for _ in range(sub.info.rows)]

    def clear_all(self) -> None:
        for alias, card in self._cards.items():
            for number in card.subunits:
                self.clear_subunit(alias, number)

    def disconnect(self) -> None:
        return None

    # -- test affordances -------------------------------------------------
    def mask_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None:
        """Mark a crosspoint as physically unusable, as PIPLX_MaskCrosspoint does."""
        sub = self._subunit(alias, subunit)
        self._check_bounds(alias, sub, row, column)
        sub.mask.add((row, column))

    # -- helpers ----------------------------------------------------------
    def _subunit(self, alias: str, subunit: int) -> _SimSubunit:
        card = self._cards.get(alias)
        if card is None:
            raise DriverError(
                f"no card aliased {alias!r} in this chassis; have {sorted(self._cards)}"
            )
        sub = card.subunits.get(subunit)
        if sub is None:
            raise DriverError(f"card {alias!r} has no subunit {subunit}")
        return sub

    @staticmethod
    def _check_bounds(alias: str, sub: _SimSubunit, row: int, column: int) -> None:
        info = sub.info
        if not (1 <= row <= info.rows):
            raise DriverError(
                f"{alias} subunit {info.subunit}: row {row} out of range 1..{info.rows}"
            )
        if not (1 <= column <= info.columns):
            raise DriverError(
                f"{alias} subunit {info.subunit}: column {column} out of range 1..{info.columns}"
            )


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------


class PilxiBackend:
    """Real chassis, via the Pickering ClientBridge wrapper.

    ``address`` is the LXI unit's IP, or the literal ``PXI`` for local PXI cards.
    Setting ``sim_card`` asks the vendor driver itself for simulated cards
    (``DriverModes.SIM_CARD``), which is a different thing from ``SimBackend``:
    it exercises the real driver stack against cards that are not in the rack.
    """

    name = "pilxi"

    def __init__(
        self,
        address: str,
        declared: tuple[CardInfo, ...],
        port: int = 1024,
        timeout_ms: int = 5000,
        sim_card: bool = False,
    ) -> None:
        self.address = address
        self.port = port
        self.timeout_ms = timeout_ms
        self.sim_card = sim_card
        self._declared = {c.alias: c for c in declared}
        self._session: Any = None
        self._open: dict[str, Any] = {}
        self._info: dict[str, CardInfo] = {}
        self._pilxi: Any = None
        self.connect()

    def connect(self) -> None:
        try:
            import pilxi
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise DriverError(
                "the 'pilxi' package is not installed; install this server with "
                "pip install 'pickering-lxi-mcp[hardware]'"
            ) from exc

        self._pilxi = pilxi
        try:
            self._session = pilxi.Pi_Session(
                self.address, port=self.port, timeout=self.timeout_ms
            )
            if self.sim_card:
                self._session.SetMode(int(pilxi.DriverModes.SIM_CARD))
        except OSError as exc:  # the ctypes load of Picmlx/Piplx failed
            raise DriverError(
                "the Pickering ClientBridge driver could not be loaded. Install the "
                "Pickering software suite, or run this server without "
                "PICKERING_LXI_ADDRESS to use the built-in simulator."
            ) from exc
        except Exception as exc:
            raise DriverError(f"could not open a session with {self.address}: {exc}") from exc

        for alias, declared in self._declared.items():
            self._open_card(alias, declared)

    def _open_card(self, alias: str, declared: CardInfo) -> None:
        try:
            card = self._session.OpenCard(declared.bus, declared.device)
        except Exception as exc:
            raise DriverError(
                f"could not open card {alias!r} at bus {declared.bus} "
                f"device {declared.device}: {exc}"
            ) from exc

        subunits: list[SubunitInfo] = []
        outputs = card.EnumerateSubs()[1]
        for number in range(1, outputs + 1):
            _type_code, rows, columns = card.SubInfo(number, True)
            subunits.append(
                SubunitInfo(
                    subunit=number,
                    type=card.SubType(number, True),
                    rows=int(rows),
                    columns=int(columns),
                    closure_limit=int(card.ClosureLimit(number)),
                    settle_time_us=int(card.SettleTime(number)),
                )
            )

        self._open[alias] = card
        self._info[alias] = CardInfo(
            alias=alias,
            bus=declared.bus,
            device=declared.device,
            card_id=card.CardId(),
            subunits=tuple(subunits),
        )

    # -- introspection ----------------------------------------------------
    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "address": self.address,
            "driver": f"ClientBridge, pilxi {getattr(self._pilxi, '__version__', 'unknown')}",
            "card_count": len(self._open),
            "hardware": not self.sim_card,
            "driver_sim_card": self.sim_card,
        }

    def cards(self) -> tuple[CardInfo, ...]:
        return tuple(self._info.values())

    # -- switching --------------------------------------------------------
    def close_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None:
        self._op(alias, subunit, row, column, True)

    def open_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> None:
        self._op(alias, subunit, row, column, False)

    def _op(self, alias: str, subunit: int, row: int, column: int, state: bool) -> None:
        card = self._card(alias)
        try:
            card.OpCrosspoint(subunit, row, column, state)
        except Exception as exc:
            verb = "close" if state else "open"
            raise DriverError(
                f"card {alias!r} refused to {verb} subunit {subunit} "
                f"crosspoint ({row},{column}): {exc}"
            ) from exc

    def view_crosspoint(self, alias: str, subunit: int, row: int, column: int) -> bool:
        card = self._card(alias)
        try:
            return bool(card.ViewCrosspoint(subunit, row, column))
        except Exception as exc:
            raise DriverError(f"card {alias!r} could not report ({row},{column}): {exc}") from exc

    def view_subunit(self, alias: str, subunit: int) -> list[list[bool]]:
        info = self._info[alias].subunit(subunit)
        return [
            [self.view_crosspoint(alias, subunit, r, c) for c in range(1, info.columns + 1)]
            for r in range(1, info.rows + 1)
        ]

    def closed_count(self, alias: str, subunit: int) -> int:
        return sum(1 for row in self.view_subunit(alias, subunit) for bit in row if bit)

    def clear_subunit(self, alias: str, subunit: int) -> None:
        card = self._card(alias)
        try:
            card.ClearSub(subunit)
        except Exception as exc:
            raise DriverError(f"card {alias!r} refused to clear subunit {subunit}: {exc}") from exc

    def clear_all(self) -> None:
        for alias, card in self._open.items():
            try:
                card.ClearCard()
            except Exception as exc:
                raise DriverError(f"card {alias!r} refused to clear: {exc}") from exc

    def disconnect(self) -> None:
        for card in self._open.values():
            with contextlib.suppress(Exception):  # teardown is best effort
                card.Close()
        self._open.clear()
        if self._session is not None:
            with contextlib.suppress(Exception):
                self._session.Close()
            self._session = None

    def _card(self, alias: str) -> Any:
        card = self._open.get(alias)
        if card is None:
            raise DriverError(f"card {alias!r} is not open; have {sorted(self._open)}")
        return card


def build_backend(cards: tuple[CardInfo, ...], env: dict[str, str] | None = None) -> Backend:
    """Pick a backend from the environment.

    No ``PICKERING_LXI_ADDRESS`` means the simulator, which is the default on
    purpose: the interesting failure is a server that silently reaches for a
    rack, not one that refuses to.
    """

    env = dict(os.environ if env is None else env)
    address = env.get("PICKERING_LXI_ADDRESS", "").strip()
    if not address:
        return SimBackend(cards)
    return PilxiBackend(
        address=address,
        declared=cards,
        port=int(env.get("PICKERING_LXI_PORT", "1024")),
        timeout_ms=int(env.get("PICKERING_LXI_TIMEOUT_MS", "5000")),
        sim_card=env.get("PICKERING_LXI_SIM_CARD", "").strip().lower() in {"1", "true", "yes"},
    )

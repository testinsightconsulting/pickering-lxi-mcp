"""An MCP server that routes signals through Pickering PXI/LXI switching."""

from .driver import Backend, CardInfo, PilxiBackend, SimBackend, SubunitInfo
from .errors import (
    DriverError,
    InterlockError,
    PathError,
    PickeringError,
    ReservationError,
    TopologyError,
)
from .factory import build_session, load_topology
from .interlocks import InterlockPolicy
from .session import ChassisSession, Route
from .tools import Tier, call, manifest
from .topology import Endpoint, Operation, SwitchPath, Topology

__all__ = [
    "Backend",
    "CardInfo",
    "ChassisSession",
    "DriverError",
    "Endpoint",
    "InterlockError",
    "InterlockPolicy",
    "Operation",
    "PathError",
    "PickeringError",
    "PilxiBackend",
    "ReservationError",
    "Route",
    "SimBackend",
    "SubunitInfo",
    "SwitchPath",
    "Tier",
    "Topology",
    "TopologyError",
    "build_session",
    "call",
    "load_topology",
    "manifest",
]
__version__ = "0.1.0"

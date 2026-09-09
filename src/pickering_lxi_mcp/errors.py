"""Error types.

Each one names a distinct refusal, because a walkthrough asserts on the class
name and an agent has to be able to tell "you may not do that" apart from "that
is not physically possible".
"""

from __future__ import annotations


class PickeringError(RuntimeError):
    """Base class for every refusal raised by this server."""


class DriverError(PickeringError):
    """The switching driver or the chassis refused an operation."""


class TopologyError(PickeringError):
    """The loaded topology is malformed, or names something that does not exist."""


class PathError(PickeringError):
    """No switch path exists between the requested endpoints."""


class InterlockError(PickeringError):
    """A safety interlock refused the operation. Nothing was switched."""


class ReservationError(PickeringError):
    """A mutating action was attempted without a valid, current reservation."""

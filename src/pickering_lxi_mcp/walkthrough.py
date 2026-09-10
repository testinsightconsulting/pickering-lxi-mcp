"""Deterministic tool walkthroughs.

A walkthrough is an ordered list of tool calls with their expected results. It
runs against the simulator, so it is fully deterministic and can be the hard
gate in CI: if a walkthrough diverges, the build fails. LLM-as-judge checks are
useful for tone and coverage, but they are advisory. This is the gate.

``expect_error`` is the half that matters most here. A switching server's job is
as much refusing as connecting, and a walkthrough that can only assert on happy
paths cannot prove an interlock fires.

A spec may also carry ``given``: crosspoints closed directly on the simulated
chassis before the run, behind the server's back. That is arranging the world,
not a step -- it is how a walkthrough can start from a rack somebody else left
switched, which is the state the recovery path exists for and the one you cannot
reach through the tool surface by definition.

A spec may also carry ``topology``: the name of a bundled topology to run
against, so a walkthrough can pin itself to the bench it describes. Omitted, the
default bundled bench is used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import tools
from .driver import build_backend
from .factory import build_session
from .session import ChassisSession
from .topology import Topology

_REF = re.compile(r"^\{\{(\w+)\.([\w.]+)\}\}$")


@dataclass
class StepResult:
    step: str
    ok: bool
    expected: Any
    actual: Any
    error: str | None = None


@dataclass
class WalkthroughResult:
    name: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    def report(self) -> str:
        lines = [f"{'PASS' if self.ok else 'FAIL'}  {self.name}"]
        for s in self.steps:
            mark = "  ok  " if s.ok else "  XX  "
            lines.append(f"{mark}{s.step}")
            if not s.ok:
                lines.append(f"        expected: {s.expected!r}")
                lines.append(f"        actual:   {s.actual!r}")
                if s.error:
                    lines.append(f"        error:    {s.error}")
        return "\n".join(lines)


def _resolve(value: Any, produced: dict[str, Any]) -> Any:
    if isinstance(value, str) and (m := _REF.match(value)):
        source, path = m.group(1), m.group(2)
        cursor: Any = produced[source]
        for part in path.split("."):
            cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
        return cursor
    if isinstance(value, dict):
        return {k: _resolve(v, produced) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, produced) for v in value]
    return value


def _matches(expected: Any, actual: Any) -> bool:
    if expected == "<any>":
        return actual is not None
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(k in actual and _matches(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            _matches(e, a) for e, a in zip(expected, actual, strict=True)
        )
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(expected) - float(actual)) < 1e-6
        except (TypeError, ValueError):
            return False
    return expected == actual


def arrange(session: ChassisSession, given: list[dict[str, Any]]) -> None:
    """Close crosspoints on the chassis without going through the server.

    Deliberately reaching past the tool layer: this is the world the server
    wakes up to, not something a caller did to it.
    """

    for cp in given:
        session.backend.close_crosspoint(
            cp["card"], int(cp["subunit"]), int(cp["row"]), int(cp["column"])
        )
    session.reconcile()


def session_for(spec: dict[str, Any]) -> ChassisSession:
    """The bench a spec runs against: the one it names, or the default."""

    name = spec.get("topology")
    if not name:
        return build_session(env={})
    topology = Topology.bundled(name)
    return ChassisSession.build(backend=build_backend(topology.cards, env={}), topology=topology)


def run(spec: dict[str, Any], session: ChassisSession | None = None) -> WalkthroughResult:
    session = session or session_for(spec)
    if spec.get("given"):
        arrange(session, spec["given"])
    result = WalkthroughResult(name=spec.get("name", "walkthrough"))
    produced: dict[str, Any] = {}

    for step in spec["steps"]:
        step_id = step.get("id") or step["tool"]
        args = _resolve(step.get("args", {}), produced)
        expected = _resolve(step.get("expect", "<any>"), produced)
        expect_error = step.get("expect_error")

        try:
            actual: Any = tools.call(session, step["tool"], **args)
        except Exception as exc:
            if expect_error and expect_error == type(exc).__name__:
                result.steps.append(StepResult(step_id, True, expect_error, type(exc).__name__))
            else:
                result.steps.append(
                    StepResult(step_id, False, expect_error or expected, None,
                               error=f"{type(exc).__name__}: {exc}")
                )
            continue

        if expect_error:
            result.steps.append(
                StepResult(step_id, False, f"{expect_error} to be raised", actual)
            )
            continue

        produced[step_id] = actual
        result.steps.append(StepResult(step_id, _matches(expected, actual), expected, actual))

    return result


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def run_all(directory: str | Path) -> list[WalkthroughResult]:
    return [run(load(p)) for p in sorted(Path(directory).glob("*.json"))]


def main() -> int:
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "walkthroughs"
    results = run_all(target)
    if not results:
        print(f"no walkthroughs found in {target!r}")
        return 1
    for r in results:
        print(r.report())
    failures = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failures)}/{len(results)} walkthroughs passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
